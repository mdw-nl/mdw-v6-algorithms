"""Parameter models: single source of truth for validation, docs and store metadata (AGENTS.md §9.1).

Each algorithm defines one Pydantic model (subclassing `V6Params`) for its `central()`
function. That model is what `make store-json` reads to generate `algorithm.json`, what
the runner validates a study file against before creating a task, and what `central()`
itself calls `parse_params` with -- so all three agree by construction instead of by
convention.
"""

from pydantic import BaseModel, ConfigDict, ValidationError


class V6Params(BaseModel):
    """Base class for an algorithm's `central()` parameter model.

    `extra="forbid"` so a typo'd parameter name is a validation error, not a silently
    ignored kwarg.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ParamsError(Exception):
    """One or more request parameters failed validation.

    Carries every problem found (Pydantic already collects them all in one pass), so
    `central()` can report them together (AGENTS.md §7.4: "report every problem at
    once, not just the first one") instead of one request-fix-retry cycle per field.
    """

    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("; ".join(messages))


def parse_params[ModelT: BaseModel](model_cls: type[ModelT], raw: dict) -> ModelT:
    """Validate `raw` against `model_cls`, raising `ParamsError` with every problem."""
    try:
        return model_cls.model_validate(raw)
    except ValidationError as exc:
        messages = [f"{'.'.join(str(p) for p in e['loc']) or '(params)'}: {e['msg']}" for e in exc.errors()]
        raise ParamsError(messages) from None
