import numpy as np
import pandas as pd
import pytest

from v6core.envelope import AlgorithmError
from v6core.spec import apply_filters, apply_inliers


def test_apply_filters_equality():
    df = pd.DataFrame({"sex": ["M", "F", "M"], "age": [20, 30, 40]})
    result = apply_filters(df, {"sex": "M"})
    assert result["age"].tolist() == [20, 40]


def test_apply_filters_isin():
    df = pd.DataFrame({"site": ["a", "b", "c"]})
    result = apply_filters(df, {"site": ["a", "c"]})
    assert result["site"].tolist() == ["a", "c"]


def test_apply_filters_range():
    df = pd.DataFrame({"age": [10, 20, 30, 40]})
    result = apply_filters(df, {"age": {"gte": 20, "lt": 40}})
    assert result["age"].tolist() == [20, 30]


def test_apply_filters_missing_column_raises():
    df = pd.DataFrame({"age": [1, 2]})
    with pytest.raises(AlgorithmError) as exc_info:
        apply_filters(df, {"missing": 1})
    assert exc_info.value.code == "MISSING_COLUMN"


def test_apply_filters_unknown_range_key_raises():
    df = pd.DataFrame({"age": [1, 2]})
    with pytest.raises(AlgorithmError) as exc_info:
        apply_filters(df, {"age": {"between": 1}})
    assert exc_info.value.code == "INVALID_PARAM"


def test_apply_filters_empty_range_dict_raises():
    df = pd.DataFrame({"age": [1, 2]})
    with pytest.raises(AlgorithmError):
        apply_filters(df, {"age": {}})


def test_apply_filters_noop_when_empty():
    df = pd.DataFrame({"age": [1, 2]})
    assert apply_filters(df, None) is df
    assert apply_filters(df, {}) is df


def test_apply_inliers_numeric_range_masks_outliers():
    df = pd.DataFrame({"age": [10, 50, 200, np.nan]})
    masked, outlier_count = apply_inliers(df, "age", [0, 120])
    assert outlier_count == 1
    assert masked.tolist()[:2] == [10, 50]
    assert pd.isna(masked.iloc[2])
    assert pd.isna(masked.iloc[3])  # existing NaN preserved, not counted as outlier


def test_apply_inliers_categorical_list():
    df = pd.DataFrame({"sex": ["M", "F", "X", None]})
    masked, outlier_count = apply_inliers(df, "sex", ["M", "F"])
    assert outlier_count == 1
    assert masked.iloc[0] == "M"
    assert masked.iloc[1] == "F"
    assert pd.isna(masked.iloc[2])
    assert pd.isna(masked.iloc[3])
