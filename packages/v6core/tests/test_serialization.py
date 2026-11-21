import math

import numpy as np
import pandas as pd

from v6core.serialization import to_jsonsafe


def test_numpy_scalars_become_native_python():
    assert to_jsonsafe(np.int64(3)) == 3
    assert isinstance(to_jsonsafe(np.int64(3)), int)
    assert to_jsonsafe(np.float64(1.5)) == 1.5


def test_nan_and_inf_become_none():
    assert to_jsonsafe(float("nan")) is None
    assert to_jsonsafe(float("inf")) is None
    assert to_jsonsafe(np.nan) is None


def test_pandas_na_becomes_none():
    assert to_jsonsafe(pd.NA) is None
    assert to_jsonsafe(pd.NaT) is None


def test_nested_structures_are_recursed():
    value = {"a": [np.int64(1), {"b": np.nan}], "c": (np.float64(2.0),)}
    result = to_jsonsafe(value)
    assert result == {"a": [1, {"b": None}], "c": [2.0]}
    assert not math.isnan(result["c"][0])


def test_numpy_array_becomes_list():
    assert to_jsonsafe(np.array([1, 2, 3])) == [1, 2, 3]
