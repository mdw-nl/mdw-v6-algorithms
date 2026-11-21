import pytest
from pydantic import Field

from v6core.params import ParamsError, V6Params, parse_params


class ExampleParams(V6Params):
    predictor_cols: list[str] = Field(min_length=1)
    min_rows: int = Field(default=5, ge=0)


def test_parse_params_returns_validated_model():
    result = parse_params(ExampleParams, {"predictor_cols": ["age"]})
    assert result.predictor_cols == ["age"]
    assert result.min_rows == 5


def test_parse_params_rejects_unknown_field():
    with pytest.raises(ParamsError):
        parse_params(ExampleParams, {"predictor_cols": ["age"], "typo_field": 1})


def test_parse_params_collects_every_error_at_once():
    with pytest.raises(ParamsError) as exc_info:
        parse_params(ExampleParams, {"predictor_cols": [], "min_rows": -1})
    assert len(exc_info.value.messages) == 2
