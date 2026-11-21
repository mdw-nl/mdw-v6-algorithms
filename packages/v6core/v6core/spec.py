"""Data-agnostic contract vocabulary (AGENTS.md §3.3): filters and inliers so far.

Binary `representation` (presence/equals/isin/invert) and categorical encoding are added
when the first algorithm that needs them is ported (logistic/Cox/KM) -- building them
now, with nothing to consume them, would just mean guessing their shape.
"""

import pandas as pd

from v6core.coerce import numeric_series
from v6core.envelope import AlgorithmError

RANGE_FILTER_KEYS = frozenset({"gte", "gt", "lte", "lt"})


def apply_filters(df: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    """Subset `df` to the rows matching every entry of `filters`.

    A filter value is:
    - a scalar: exact equality
    - a list: `isin`
    - a dict of `gte`/`gt`/`lte`/`lt`: a numeric range (the column is coerced to
      numeric first)

    A missing filter column or a malformed range spec raises `AlgorithmError` --
    filters apply to every statistic in the request, so a bad one invalidates the
    whole node result, not just one column's.
    """
    if not filters:
        return df

    working = df
    for column, value in filters.items():
        if column not in working.columns:
            raise AlgorithmError("MISSING_COLUMN", "node", f"Filter column '{column}' not found in dataset")
        if isinstance(value, dict):
            unknown = set(value) - RANGE_FILTER_KEYS
            if unknown:
                raise AlgorithmError(
                    "INVALID_PARAM",
                    "node",
                    f"Unknown range filter key(s) {sorted(unknown)} for column '{column}'; "
                    f"expected any of {sorted(RANGE_FILTER_KEYS)}",
                )
            if not value:
                raise AlgorithmError(
                    "INVALID_PARAM",
                    "node",
                    f"Range filter for column '{column}' must include at least one of "
                    f"{sorted(RANGE_FILTER_KEYS)}",
                )
            numeric_column, error = numeric_series(working, column)
            if error is not None:
                raise AlgorithmError("NON_NUMERIC", "node", error.message)
            mask = pd.Series(True, index=working.index)
            if "gte" in value:
                mask &= numeric_column >= value["gte"]
            if "gt" in value:
                mask &= numeric_column > value["gt"]
            if "lte" in value:
                mask &= numeric_column <= value["lte"]
            if "lt" in value:
                mask &= numeric_column < value["lt"]
            working = working[mask]
        elif isinstance(value, list):
            working = working[working[column].isin(value)]
        else:
            working = working[working[column] == value]
    return working


def _is_numeric_range(inliers: list) -> bool:
    return len(inliers) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in inliers)


def apply_inliers(df: pd.DataFrame, column: str, inliers: list) -> tuple[pd.Series, int]:
    """Mask values of `df[column]` outside `inliers` to NaN.

    `inliers` is a `[min, max]` numeric range when it's exactly two non-bool numbers,
    otherwise an explicit list of allowed categorical values. Existing NaNs are never
    counted as outliers.

    Returns `(masked_series, outlier_count)`.
    """
    series = df[column]
    if _is_numeric_range(inliers):
        low, high = sorted(inliers)
        is_inlier = pd.to_numeric(series, errors="coerce").between(low, high)
    else:
        is_inlier = series.isin(inliers)
    is_inlier = is_inlier | series.isna()
    outlier_count = int((~is_inlier).sum())
    return series.where(is_inlier), outlier_count
