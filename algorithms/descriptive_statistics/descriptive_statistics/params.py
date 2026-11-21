"""Parameter model for `descriptive_statistics.central()` (AGENTS.md §9.1).

Single source of truth: this model is what `central()` validates requests against,
what `make store-json` will read to generate `algorithm.json`, and what the runner
validates a study file against before creating a task.
"""

from typing import Any

from pydantic import Field, model_validator

from v6core.params import V6Params

# Quantiles are deliberately not offered yet: unlike every statistic below, a quantile
# cannot be combined from per-node sufficient statistics into the exact pooled value --
# only estimated (e.g. local bootstrap + inverse-variance meta-analysis, as the legacy
# `fed_statistics` did). That conflicts with this repo's "federated must equal pooled"
# rule (AGENTS.md §3.1/§10.1) for every other statistic in this image. Revisit this as
# a deliberate, documented exception (like the Cox exact-event-times one, §8.1) rather
# than silently shipping an approximate statistic next to exact ones.
STATISTIC_NAMES = (
    "counts",
    "binned_counts",
    "minmax",
    "mean",
    "std",
    "nrows",
    "nans",
    "outliers",
)


class ColumnStatsSpec(V6Params):
    """What to compute for one column."""

    stats: list[str] = Field(min_length=1, description="Statistics to compute for this column.")
    bins: list[float] | None = Field(default=None, description="Bin edges, required by 'binned_counts'.")
    min_cap: float | None = Field(default=None, description="Lower bound 'minmax' is capped to.")
    max_cap: float | None = Field(default=None, description="Upper bound 'minmax' is capped to.")
    inliers: list[Any] | None = Field(
        default=None,
        description=(
            "A [min, max] numeric range, or an explicit list of allowed categorical values. "
            "Values outside it are excluded from every other statistic for this column and "
            "counted separately (request the 'outliers' statistic to get that count)."
        ),
    )

    @model_validator(mode="after")
    def _check_stats(self) -> "ColumnStatsSpec":
        unknown = sorted(set(self.stats) - set(STATISTIC_NAMES))
        if unknown:
            raise ValueError(f"unknown statistic(s) {unknown}; expected one of {STATISTIC_NAMES}")
        if "binned_counts" in self.stats and (self.bins is None or len(self.bins) < 2):
            raise ValueError("'binned_counts' requires at least two 'bins' edges")
        if "outliers" in self.stats and self.inliers is None:
            raise ValueError("'outliers' requires 'inliers' to be set")
        return self


class DescriptiveStatisticsParams(V6Params):
    """Parameters for the `descriptive_statistics` central function."""

    statistics: dict[str, ColumnStatsSpec] = Field(
        min_length=1, description="Per-column statistics to compute: {column: {stats: [...], ...}}."
    )
    filters: dict[str, Any] | None = Field(
        default=None, description="Row filters applied before every statistic: equality, isin, or a range."
    )
    organizations: list[str] | None = Field(
        default=None, description="Organization names to include; omit for every organization."
    )
    min_organizations: int = Field(
        default=1, ge=1, description="Minimum organizations required to report a result."
    )
    min_rows: int | None = Field(
        default=None,
        description="Minimum usable rows per node (after filters); below it, the node is excluded.",
    )
    min_cell_count: int | None = Field(
        default=None, description="Minimum count to release a cell/category unsuppressed."
    )
    max_categories: int | None = Field(
        default=None,
        description="Maximum distinct category labels 'counts' releases; the rest are merged into '<other>'.",
    )
    timeout_s: float = Field(
        default=300.0, gt=0, description="Seconds to wait for each node before timing out."
    )
