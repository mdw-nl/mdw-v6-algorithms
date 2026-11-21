"""Column presence and numeric-coercion checks (AGENTS.md §3.2).

Two tiers, by design:
- `require_columns` raises `AlgorithmError` -- use it for columns whose absence makes
  the *whole* request meaningless (e.g. a filter column), so the node fails cleanly
  instead of silently using the wrong rows.
- `check_column_present` / `numeric_series` return a `NodeError | None` instead of
  raising -- use these per-column, so one bad column doesn't take down every other
  column's statistics (AGENTS.md §1.3).
"""

import pandas as pd

from v6core.envelope import AlgorithmError, NodeError


def require_columns(df: pd.DataFrame, columns: list[str], *, scope: str = "node") -> None:
    """Raise `AlgorithmError(MISSING_COLUMN)` if any of `columns` is absent from `df`."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise AlgorithmError(
            "MISSING_COLUMN",
            scope,
            f"Column(s) {missing} not found in dataset; available columns: {list(df.columns)}",
        )


def check_column_present(df: pd.DataFrame, column: str) -> NodeError | None:
    """Per-column presence check that returns an error instead of raising."""
    if column not in df.columns:
        return NodeError(
            "MISSING_COLUMN",
            f"column:{column}",
            f"Column '{column}' not found in dataset; available columns: {list(df.columns)}",
        )
    return None


def numeric_series(df: pd.DataFrame, column: str) -> tuple[pd.Series, NodeError | None]:
    """Coerce `df[column]` to numeric.

    Returns `(series, None)` on success, or `(df[column], NodeError(NON_NUMERIC, ...))`
    if any non-null value fails to convert -- the original column is returned unchanged
    so the caller can decide whether to skip just the statistics that need it to be
    numeric.
    """
    source = df[column]
    converted = pd.to_numeric(source, errors="coerce")
    invalid = source.notna() & converted.isna()
    if invalid.any():
        return source, NodeError(
            "NON_NUMERIC",
            f"column:{column}",
            f"Column '{column}' contains non-numeric values and cannot be used for numeric statistics",
        )
    return converted, None
