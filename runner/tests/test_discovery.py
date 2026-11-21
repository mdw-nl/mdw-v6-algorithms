import pytest

from v6run.discovery import ParamsModelNotFoundError, find_params_model


def test_finds_descriptive_statistics_top_level_model():
    discovered = find_params_model("descriptive_statistics")

    assert discovered.model.__name__ == "DescriptiveStatisticsParams"
    assert "statistics" in discovered.model.model_fields
    # The nested ColumnStatsSpec must not be picked instead.
    assert "stats" not in discovered.model.model_fields


def test_unknown_algorithm_raises_clear_error():
    with pytest.raises(ParamsModelNotFoundError, match="does_not_exist"):
        find_params_model("does_not_exist")
