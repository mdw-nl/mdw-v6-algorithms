import pandas as pd
import pytest

from v6core.coerce import check_column_present, numeric_series, require_columns
from v6core.envelope import AlgorithmError


def test_require_columns_passes_when_present():
    df = pd.DataFrame({"age": [1, 2]})
    require_columns(df, ["age"])  # no raise


def test_require_columns_raises_missing_column():
    df = pd.DataFrame({"age": [1, 2]})
    with pytest.raises(AlgorithmError) as exc_info:
        require_columns(df, ["age", "weight"], scope="node")
    assert exc_info.value.code == "MISSING_COLUMN"
    assert exc_info.value.scope == "node"
    assert "weight" in exc_info.value.message


def test_check_column_present_returns_scoped_error():
    df = pd.DataFrame({"age": [1, 2]})
    error = check_column_present(df, "missing")
    assert error is not None
    assert error.code == "MISSING_COLUMN"
    assert error.scope == "column:missing"


def test_check_column_present_returns_none_when_ok():
    df = pd.DataFrame({"age": [1, 2]})
    assert check_column_present(df, "age") is None


def test_numeric_series_coerces_clean_numbers():
    df = pd.DataFrame({"age": ["1", "2", "3"]})
    series, error = numeric_series(df, "age")
    assert error is None
    assert series.tolist() == [1.0, 2.0, 3.0]


def test_numeric_series_flags_non_numeric_values():
    df = pd.DataFrame({"age": ["1", "oops", "3"]})
    series, error = numeric_series(df, "age")
    assert error is not None
    assert error.code == "NON_NUMERIC"
    assert error.scope == "column:age"


def test_numeric_series_ignores_existing_nan():
    df = pd.DataFrame({"age": ["1", None, "3"]})
    series, error = numeric_series(df, "age")
    assert error is None
