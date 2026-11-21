"""Pure statistics for `descriptive_statistics` (AGENTS.md §3.1): no vantage6 imports.

`local_statistics` runs on one node's `pandas.DataFrame`; `aggregate_statistics` combines
the per-node results centrally. Every statistic here recombines to the *exact* pooled
value (sums, counts, min/max) -- see `params.py` for why quantiles aren't offered yet.

Privacy (AGENTS.md §8): a node contributes a statistic only when the rows backing it
clear `min_cell_count`; `counts`/`binned_counts` release a `[lower, upper]` range instead
of an exact number when a category falls short; `minmax` is always capped or rounded,
never the exact value, even with no `min_cap`/`max_cap` given.
"""

import numpy as np
import pandas as pd

from v6core import coerce, privacy, spec
from v6core.envelope import AlgorithmError, NodeError

# When a request gives no explicit min_cap/max_cap, minmax is rounded to this many
# significant figures instead of being released at full float precision -- the "do
# instead: capped/rounded bounds" mitigation from AGENTS.md §8.1's exact-min/max row.
DEFAULT_MINMAX_SIG_FIGS = 2


def _round_sig(value: float, sig_figs: int) -> float:
    if value == 0 or not np.isfinite(value):
        return value
    digits = sig_figs - int(np.floor(np.log10(abs(value)))) - 1
    return float(round(value, digits))


def _suppressed_range(count: int, threshold: int) -> dict:
    if count < threshold:
        return {"lower": 0, "upper": threshold}
    return {"lower": count, "upper": count}


def _compute_counts(series: pd.Series, min_cell_count: int, max_categories: int) -> dict:
    # A unique or rare raw value (a free-text field, an ID-like column) would otherwise
    # leak as a category *label* even though its count is suppressed -- small-cell
    # suppression only hides the count, not the fact that the label exists at all
    # (AGENTS.md §10.5's canary test). So a below-threshold category is merged into
    # "<other>" unconditionally, regardless of `max_categories`; `max_categories` then
    # separately caps how many of the *remaining* (large-enough) categories are shown
    # individually, merging any further overflow into the same bucket.
    value_counts = series.dropna().value_counts(dropna=False)
    large = value_counts[value_counts >= min_cell_count]
    small = value_counts[value_counts < min_cell_count]
    kept = large.iloc[: max(max_categories - 1, 0)]
    overflow = pd.concat([large.iloc[max(max_categories - 1, 0) :], small])
    counts = {str(label): {"lower": int(count), "upper": int(count)} for label, count in kept.items()}
    if len(overflow) > 0:
        counts["<other>"] = _suppressed_range(int(overflow.sum()), min_cell_count)
    return counts


def _compute_binned_counts(numeric_series: pd.Series, bins: list[float], min_cell_count: int) -> dict:
    values = numeric_series.dropna().astype(float).to_numpy()
    counts, edges = np.histogram(values, bins=np.asarray(sorted(bins), dtype=float))
    result = {}
    for count, left, right in zip(counts, edges[:-1], edges[1:], strict=True):
        if np.isneginf(left):
            label = f"< {right:g}"
        elif np.isposinf(right):
            label = f">= {left:g}"
        else:
            label = f"{left:g}-{right:g}"
        result[label] = _suppressed_range(int(count), min_cell_count)
    return result


def _compute_minmax(
    numeric_series: pd.Series, min_cap: float | None, max_cap: float | None, min_cell_count: int
):
    values = numeric_series.dropna()
    if len(values) < min_cell_count:
        return {"min": None, "max": None}
    minimum, maximum = float(values.min()), float(values.max())
    if min_cap is not None:
        minimum = max(minimum, min_cap)
    else:
        minimum = _round_sig(minimum, DEFAULT_MINMAX_SIG_FIGS)
    if max_cap is not None:
        maximum = min(maximum, max_cap)
    else:
        maximum = _round_sig(maximum, DEFAULT_MINMAX_SIG_FIGS)
    return {"min": minimum, "max": maximum}


def _compute_mean(numeric_series: pd.Series, min_cell_count: int) -> dict:
    values = numeric_series.dropna()
    if len(values) < min_cell_count:
        return {"sum": None, "n": None}
    return {"sum": float(values.sum()), "n": int(len(values))}


def _compute_std(numeric_series: pd.Series, min_cell_count: int) -> dict:
    values = numeric_series.dropna()
    if len(values) < min_cell_count:
        return {"sumsq": None, "sum": None, "n": None}
    return {
        "sumsq": float(np.square(values.to_numpy()).sum()),
        "sum": float(values.sum()),
        "n": int(len(values)),
    }


def _compute_nrows(numeric_count: int, min_cell_count: int) -> dict:
    return privacy.suppressed_count(numeric_count, min_cell_count)


STAT_NEEDS_NUMERIC = {"minmax", "mean", "std", "binned_counts"}


def _column_statistics(
    df: pd.DataFrame,
    column: str,
    column_spec: dict,
    min_cell_count: int,
    max_categories: int,
) -> tuple[dict, list[NodeError]]:
    errors: list[NodeError] = []
    raw_series = df[column]

    masked = raw_series
    outlier_count = 0
    if column_spec.get("inliers") is not None:
        masked, outlier_count = spec.apply_inliers(df, column, column_spec["inliers"])

    # Coerced unconditionally (cheap, never raises) rather than only when a numeric
    # statistic is requested: that keeps `numeric_masked` a plain `pd.Series` instead
    # of `pd.Series | None`, since every branch below that reads it is already gated
    # on `statistic in STAT_NEEDS_NUMERIC`.
    numeric_masked, numeric_error = coerce.numeric_series(pd.DataFrame({column: masked}), column)

    results: dict = {}
    for statistic in column_spec["stats"]:
        if statistic in STAT_NEEDS_NUMERIC and numeric_error is not None:
            errors.append(
                NodeError(
                    numeric_error.code,
                    f"statistic:{column}.{statistic}",
                    numeric_error.message,
                )
            )
            continue
        if statistic == "counts":
            results[statistic] = _compute_counts(masked, min_cell_count, max_categories)
        elif statistic == "binned_counts":
            # `ColumnStatsSpec` already guarantees >=2 bin edges whenever
            # 'binned_counts' is requested (see params.py's model_validator).
            bins = column_spec.get("bins")
            assert isinstance(bins, list)
            results[statistic] = _compute_binned_counts(numeric_masked, bins, min_cell_count)
        elif statistic == "minmax":
            results[statistic] = _compute_minmax(
                numeric_masked, column_spec.get("min_cap"), column_spec.get("max_cap"), min_cell_count
            )
        elif statistic == "mean":
            results[statistic] = _compute_mean(numeric_masked, min_cell_count)
        elif statistic == "std":
            results[statistic] = _compute_std(numeric_masked, min_cell_count)
        elif statistic == "nrows":
            results[statistic] = _compute_nrows(int(masked.notna().sum()), min_cell_count)
        elif statistic == "nans":
            # Structural NaNs on the pre-mask column: a value excluded by `inliers`
            # is an outlier, not double-counted as nan.
            results[statistic] = _compute_nrows(int(raw_series.isna().sum()), min_cell_count)
        elif statistic == "outliers":
            results[statistic] = _compute_nrows(outlier_count, min_cell_count)
    return results, errors


def local_statistics(
    df: pd.DataFrame,
    statistics: dict[str, dict],
    filters: dict | None,
    min_cell_count: int,
    max_categories: int,
) -> tuple[dict, list[NodeError]]:
    """Compute this node's contribution to every requested column/statistic.

    Raises `AlgorithmError` for whole-request problems (a bad filter column -- see
    `v6core.spec.apply_filters` -- or no rows left after filtering). A missing column
    or a column that can't be coerced to numeric for a statistic that needs it is
    instead returned as a scoped `NodeError`, so it only knocks out that column (or
    that one statistic) rather than the whole node (AGENTS.md §1.3).
    """
    working = spec.apply_filters(df, filters)
    if working.empty:
        raise AlgorithmError("EMPTY_AFTER_FILTER", "node", "No rows remain after applying 'filters'")

    errors: list[NodeError] = []
    columns: dict = {}
    for column, column_spec in statistics.items():
        column_error = coerce.check_column_present(working, column)
        if column_error is not None:
            errors.append(column_error)
            continue
        column_result, column_errors = _column_statistics(
            working, column, column_spec, min_cell_count, max_categories
        )
        errors.extend(column_errors)
        if column_result:
            columns[column] = column_result

    # `row_count` is used internally (by `central()`'s `min_rows` floor) and must
    # never be copied into the user-facing result -- it's exact and unsuppressed,
    # and a single patient at a small site could be reverse-identified from the
    # combination of a node's row count and its other released statistics.
    return {"row_count": int(len(working)), "columns": columns}, errors


def _aggregate_ranged_counts(local_values: list[dict]) -> dict:
    combined: dict = {}
    for value in local_values:
        for label, bounds in value.items():
            if label in combined:
                combined[label] = {
                    "lower": combined[label]["lower"] + bounds["lower"],
                    "upper": combined[label]["upper"] + bounds["upper"],
                }
            else:
                combined[label] = dict(bounds)
    return combined


def _aggregate_minmax(local_values: list[dict]) -> dict:
    mins = [v["min"] for v in local_values if v.get("min") is not None]
    maxes = [v["max"] for v in local_values if v.get("max") is not None]
    return {"min": min(mins) if mins else None, "max": max(maxes) if maxes else None}


def _aggregate_mean(local_values: list[dict]) -> float | None:
    usable = [v for v in local_values if v.get("sum") is not None and v.get("n") is not None]
    total_n = sum(v["n"] for v in usable)
    if total_n == 0:
        return None
    return sum(v["sum"] for v in usable) / total_n


def _aggregate_std(local_values: list[dict]) -> float | None:
    usable = [v for v in local_values if v.get("n") is not None]
    total_n = sum(v["n"] for v in usable)
    if total_n < 2:
        return None
    total_sum = sum(v["sum"] for v in usable)
    total_sumsq = sum(v["sumsq"] for v in usable)
    mean = total_sum / total_n
    variance_population = max((total_sumsq / total_n) - mean**2, 0.0)
    variance_sample = variance_population * (total_n / (total_n - 1))
    return float(np.sqrt(variance_sample))


def _aggregate_suppressed_count(local_values: list[dict]) -> dict:
    usable = [v["value"] for v in local_values if v.get("value") is not None]
    if not usable:
        return {"value": None, "suppressed": True}
    return {"value": sum(usable)}


_AGGREGATORS = {
    "counts": _aggregate_ranged_counts,
    "binned_counts": _aggregate_ranged_counts,
    "minmax": _aggregate_minmax,
    "mean": _aggregate_mean,
    "std": _aggregate_std,
    "nrows": _aggregate_suppressed_count,
    "nans": _aggregate_suppressed_count,
    "outliers": _aggregate_suppressed_count,
}


def aggregate_statistics(
    local_results: list[dict],
    statistics: dict[str, dict],
) -> tuple[dict, list[str]]:
    """Combine qualifying nodes' `local_statistics()` results into the final output.

    `local_results` is each qualifying node's `{"row_count": ..., "columns": {...}}`
    (organizations excluded by `min_rows`/quorum must already be filtered out by the
    caller). A column/statistic missing from some nodes (suppressed, or the column
    wasn't present there) is aggregated from whichever nodes do have it; if none do,
    the result is `null` with a warning, never a crash.
    """
    warnings: list[str] = []
    columns: dict = {}
    for column, column_spec in statistics.items():
        column_result = {}
        for statistic in column_spec["stats"]:
            values = [
                r["columns"][column][statistic]
                for r in local_results
                if column in r["columns"] and statistic in r["columns"][column]
            ]
            missing = len(local_results) - len(values)
            if missing:
                warnings.append(
                    f"Column '{column}' statistic '{statistic}' was missing or "
                    f"suppressed on {missing} node(s)."
                )
            column_result[statistic] = _AGGREGATORS[statistic](values) if values else None
        columns[column] = column_result
    return columns, warnings
