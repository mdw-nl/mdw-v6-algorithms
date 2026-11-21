"""Make numpy/pandas values JSON-safe (AGENTS.md §9.2: no numpy scalars, NaN -> null)."""

import math
from typing import Any

import numpy as np
import pandas as pd


def to_jsonsafe(value: Any) -> Any:
    """Recursively convert `value` into something `json.dumps` can serialize.

    - numpy scalars/arrays -> native Python types (`.item()` / `.tolist()`)
    - NaN/Inf floats and pandas NA/NaT -> `None` (JSON has no NaN)
    - dict/list/tuple -> recursed into, preserving dict key order
    - everything else is returned unchanged
    """
    if value is None:
        return None
    if isinstance(value, np.generic):
        return to_jsonsafe(value.item())
    if isinstance(value, np.ndarray):
        return [to_jsonsafe(v) for v in value.tolist()]
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is pd.NA or value is pd.NaT:
        return None
    try:
        if np.isscalar(value) and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {key: to_jsonsafe(v) for key, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonsafe(v) for v in value]
    return value
