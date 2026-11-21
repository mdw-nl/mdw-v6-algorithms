import pandas as pd
import pytest

from v6core.privacy import (
    ABSOLUTE_MINIMUMS,
    DEFAULTS,
    PrivacyParamError,
    data_fingerprint,
    deterministic_pick,
    resolve_threshold,
    suppressed_count,
)


def test_resolve_threshold_uses_default_when_not_requested():
    value, below_default = resolve_threshold("min_cell_count", None)
    assert value == DEFAULTS.min_cell_count
    assert below_default is False


def test_resolve_threshold_allows_lowering_to_absolute_minimum():
    minimum = ABSOLUTE_MINIMUMS["min_cell_count"]
    value, below_default = resolve_threshold("min_cell_count", minimum)
    assert value == minimum
    assert below_default is True


def test_resolve_threshold_rejects_below_absolute_minimum():
    minimum = ABSOLUTE_MINIMUMS["min_cell_count"]
    with pytest.raises(PrivacyParamError):
        resolve_threshold("min_cell_count", minimum - 1)


def test_suppressed_count_hides_small_values():
    assert suppressed_count(2, threshold=5) == {"value": None, "suppressed": True}


def test_suppressed_count_reveals_values_at_or_above_threshold():
    assert suppressed_count(5, threshold=5) == {"value": 5}


def test_data_fingerprint_is_deterministic_and_data_only():
    df_a = pd.DataFrame({"age": [1, 2, 3], "sex": ["M", "F", "M"]})
    df_b = pd.DataFrame({"age": [9, 9, 9], "sex": ["X", "X", "X"]})  # same shape/columns
    assert data_fingerprint(df_a) == data_fingerprint(df_b)

    df_c = pd.DataFrame({"age": [1, 2], "sex": ["M", "F"]})  # different row count
    assert data_fingerprint(df_a) != data_fingerprint(df_c)


def test_deterministic_pick_is_stable_and_bounded():
    picks = {deterministic_pick("fingerprint", "col", modulus=7) for _ in range(5)}
    assert len(picks) == 1
    assert next(iter(picks)) in range(7)
