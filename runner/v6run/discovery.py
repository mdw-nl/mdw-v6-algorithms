"""Find an algorithm's single top-level params model (AGENTS.md §9.1).

Each algorithm exposes `<algorithm>.params`, a module containing one or more
`pydantic.BaseModel` subclasses of `v6core.params.V6Params`. Exactly one of those is
the model for the algorithm's `central()` kwargs -- the others (if any) are nested specs
used as a field type inside it (e.g. `descriptive_statistics`'s `ColumnStatsSpec`, used
as the value type of `DescriptiveStatisticsParams.statistics`).

Nested models are told apart from the top-level one by: do they appear as a field's
annotated type (or inside a `list[...]`/`dict[str, ...]`/`X | None` wrapping it) on
another candidate in the same module? The one candidate that is never referenced that
way is the top-level model. If the naming convention `<PascalCase(name)>Params` matches
a class in the module, that's checked first as a fast path -- it's what every algorithm
in this repo actually uses, and it resolves the (rare) case of a module exporting two
top-level-looking models unambiguously.
"""

import importlib
import inspect
import typing
from dataclasses import dataclass

from pydantic import BaseModel

from v6core.params import V6Params


class ParamsModelNotFoundError(Exception):
    """Raised when an algorithm's `<algorithm>.params` module, or its top-level
    params model, cannot be located or disambiguated."""


@dataclass(frozen=True, slots=True)
class DiscoveredParamsModel:
    algorithm: str
    model: type[BaseModel]
    module_name: str


def _to_pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _local_v6params_subclasses(module) -> list[type[BaseModel]]:
    candidates = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj is V6Params:
            continue
        if not issubclass(obj, V6Params):
            continue
        if obj.__module__ != module.__name__:
            continue  # imported from elsewhere (e.g. V6Params itself, or a shared spec)
        candidates.append(obj)
    return candidates


def _referenced_types(model: type[BaseModel]) -> set[type]:
    """Every type reachable by unwrapping a field's annotation through Optional/list/dict."""
    found: set[type] = set()
    for field in model.model_fields.values():
        _unwrap(field.annotation, found)
    return found


def _unwrap(annotation, found: set[type]) -> None:
    if annotation is None:
        return
    args = typing.get_args(annotation)
    if args:
        for arg in args:
            _unwrap(arg, found)
    elif isinstance(annotation, type):
        found.add(annotation)


def find_params_model(algorithm: str) -> DiscoveredParamsModel:
    """Locate the top-level params model for `algorithm` (e.g. 'descriptive_statistics').

    Raises `ParamsModelNotFoundError` if the module can't be imported, or if no model
    (or more than one, ambiguously) can be identified as the top-level one.
    """
    module_name = f"{algorithm}.params"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ParamsModelNotFoundError(
            f"Could not import '{module_name}'. Is the '{algorithm}' package installed in "
            f"this environment? (e.g. `uv sync`, or `pip install -e algorithms/{algorithm}`)"
        ) from exc

    expected_name = f"{_to_pascal_case(algorithm)}Params"
    fast_path = getattr(module, expected_name, None)
    if (
        isinstance(fast_path, type)
        and issubclass(fast_path, V6Params)
        and fast_path.__module__ == module_name
    ):
        return DiscoveredParamsModel(algorithm=algorithm, model=fast_path, module_name=module_name)

    candidates = _local_v6params_subclasses(module)
    if not candidates:
        raise ParamsModelNotFoundError(f"No subclass of v6core.params.V6Params found in '{module_name}'.")

    referenced: set[type] = set()
    for candidate in candidates:
        referenced |= _referenced_types(candidate)
    top_level = [c for c in candidates if c not in referenced]

    if len(top_level) == 1:
        return DiscoveredParamsModel(algorithm=algorithm, model=top_level[0], module_name=module_name)

    names = ", ".join(c.__name__ for c in candidates)
    raise ParamsModelNotFoundError(
        f"Could not unambiguously identify the top-level params model in '{module_name}' "
        f"(candidates: {names}). Expected a class named '{expected_name}'."
    )
