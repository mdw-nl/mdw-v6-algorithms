# descriptive_statistics

Federated descriptive statistics over arbitrary columns: counts, binned counts,
min/max, mean, standard deviation, row counts, NaN counts, and outlier counts.
Replaces the legacy `fed_statistics` and `average` algorithms (`average`'s single-column
mean is one of this image's statistics).

Every statistic here recombines from per-node sufficient statistics to the **exact**
pooled value — there is no approximation step. **Quantiles are not offered**: unlike
every statistic above, a quantile can't be combined from per-node sufficient statistics
into the exact pooled value (only estimated, e.g. by local bootstrapping plus a
meta-analytic combination, as the legacy algorithm did). That conflicts with this
image's "federated equals pooled" guarantee, so it's left out rather than silently
shipped as the one approximate statistic next to seven exact ones. Revisit this as a
deliberate, documented exception if a project needs it.

## Parameters

See `descriptive_statistics/params.py` (`DescriptiveStatisticsParams`) for the single
source of truth — field descriptions there double as this table.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `statistics` | `dict[str, ColumnStatsSpec]` | required | `{column: {stats: [...], bins, min_cap, max_cap, inliers}}`. |
| `filters` | `dict \| null` | `null` | Equality, `isin`, or a `{gte,gt,lte,lt}` range, applied before every statistic. |
| `organizations` | `list[str] \| null` | `null` (all) | Restrict the fan-out to these organization names. |
| `min_organizations` | `int` | `1` | Quorum: fewer qualifying organizations is a clean `QUORUM_NOT_MET` error. |
| `min_rows` | `int \| null` | privacy default (5) | Per-node floor on usable rows; below it, the node is excluded entirely. |
| `min_cell_count` | `int \| null` | privacy default (5) | Minimum count to release a cell/category unsuppressed. |
| `max_categories` | `int \| null` | privacy default (20) | Categories beyond the most frequent this many are merged into `"<other>"`. |
| `timeout_s` | `float` | `300` | Per-node wait before that node is marked `TIMEOUT`. |

### `ColumnStatsSpec.stats`

`counts`, `binned_counts` (needs `bins`, ≥2 edges), `minmax` (optionally capped via
`min_cap`/`max_cap`), `mean`, `std`, `nrows`, `nans`, `outliers` (needs `inliers`).

`inliers` is a `[min, max]` numeric range, or an explicit list of allowed categorical
values; values outside it are excluded from every other statistic for that column and
counted separately under `outliers`.

Each statistic is computed as a separate complete-case aggregation: a column that fails
coercion on one node (e.g. `NON_NUMERIC`) drops that node from `mean`/`std`/`minmax` for
that column, while `nrows`/`counts` for the same column are unaffected if they don't
require numeric coercion. This means different statistics for the same column can carry
different effective sample sizes when a node partially fails — read `warnings` to see
which nodes were excluded from which statistic; don't assume `nrows` is the denominator
for every other statistic on that column.

## Output shape

```json
"result": {
  "columns": {
    "age": {
      "mean": 49.8, "std": 15.1,
      "minmax": {"min": 0.0, "max": 90.0},
      "nrows": {"value": 1500}
    },
    "sex": {"counts": {"F": {"lower": 729, "upper": 729}, "M": {"lower": 771, "upper": 771}}}
  }
}
```

`counts`/`binned_counts` entries are always `{"lower": n, "upper": n}` (equal when the
count clears `min_cell_count`, otherwise `{"lower": 0, "upper": min_cell_count}`).
`nrows`/`nans`/`outliers` use the standard `{"value": n}` / `{"value": null,
"suppressed": true}` shape (AGENTS.md §9.2).

## Privacy (AGENTS.md §8)

- **Small counts never appear under their own label.** A category whose count is below
  `min_cell_count` is merged into `"<other>"` rather than shown with a suppressed-range
  display — showing even a suppressed range under a rare label's own name would still
  leak that the label exists in the data (the canary test in `tests/test_core.py`
  checks this directly). `max_categories` separately caps how many of the
  *large-enough* categories are shown individually.
- **`minmax` is always capped or rounded**, never released at full precision, even
  with no `min_cap`/`max_cap` given (it's rounded to 2 significant figures by
  default) — the legacy algorithm only did this when a cap was explicitly requested.
- **Row count is internal only.** Each node's exact row count is used to apply
  `min_rows` and is never copied into the user-facing result.
- **No secondary suppression (yet).** The legacy algorithm's secondary suppression
  derived its perturbation key from a request parameter, which defeats the point (a
  requester could predict or choose it). `v6core.privacy.data_fingerprint`/
  `deterministic_pick` provide a data-derived alternative, but it isn't wired into this
  image yet — only primary (per-category) threshold suppression and rare-category
  merging are implemented.

## Testing

- `tests/test_core.py`: federated-equals-pooled (exact, tight tolerance), privacy
  (suppression, canary, rare-category merging), fault isolation (a missing column or
  non-numeric column only drops that column/statistic, not the whole node).
- `tests/test_entrypoints.py`: the same, through the vantage6 mock network
  (`MockAlgorithmClient`) — participation, quorum, the provenance guard.
- `make smoke IMAGE=descriptive_statistics` runs `examples/studies/descriptive_statistics.yaml`
  against the real dev network (`healthy` and `faulty` scenarios); both have been run
  manually against a live 4-organization network (3 nodes + 1 node-less) with correct
  participation, aggregation and fault-isolation.
