# Changelog

All notable changes to `descriptive_statistics` are documented here. Versioning is
per-image semver (AGENTS.md §11): a breaking change to params or output shape is a
major bump.

## 0.1.0 - 2026-11-21

Initial release, porting the legacy `fed_statistics` and `average` onto `v6core`.

### Added
- `counts`, `binned_counts`, `minmax`, `mean`, `std`, `nrows`, `nans`, `outliers`
  statistics over arbitrary columns, with `filters` and `inliers`.

### Fixed (vs. the legacy algorithms, AGENTS.md §14)
- `minmax` is now always capped or rounded, never released at raw precision.
- Row count is no longer exposed in the output (used internally for `min_rows` only).
- Rare/small categories are merged into `"<other>"` instead of shown with a suppressed
  count under their own label (a label-only disclosure the legacy suppression missed).
- One bad column (missing, or non-numeric for a statistic that needs it) only drops
  that column/statistic; it no longer fails the whole node.
- Uses the standard envelope, parameter names and privacy threshold model (AGENTS.md
  §7.1, §9.1, §8.4) instead of raising `ValueError`/returning ad hoc `{"error": ...}`.

### Not included
- Quantiles (see README: no exact pooled-equivalent method exists yet).
- Secondary/deterministic-noise suppression (the primitives exist in
  `v6core.privacy`, not wired into this image).
