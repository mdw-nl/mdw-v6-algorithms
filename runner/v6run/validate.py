"""Offline study validation (AGENTS.md §9.4): no server connection needed."""

from dataclasses import dataclass, field

from pydantic import ValidationError

from v6core.params import ParamsError, parse_params
from v6run.discovery import ParamsModelNotFoundError, find_params_model
from v6run.study import Study, load_study


@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    study: Study | None = None


def validate(study_path: str) -> ValidationResult:
    """Validate a study file's shape and its `params` against the algorithm's model.

    Never raises for an invalid study -- every problem is collected into
    `ValidationResult.problems` (AGENTS.md §7.4: report every problem at once).
    """
    problems: list[str] = []

    try:
        study = load_study(study_path)
    except ValidationError as exc:
        for error in exc.errors():
            loc = ".".join(str(p) for p in error["loc"]) or "(study file)"
            problems.append(f"{loc}: {error['msg']}")
        return ValidationResult(ok=False, problems=problems)
    except (OSError, ValueError) as exc:
        return ValidationResult(ok=False, problems=[str(exc)])

    try:
        discovered = find_params_model(study.algorithm)
    except ParamsModelNotFoundError as exc:
        return ValidationResult(ok=False, problems=[str(exc)], study=study)

    try:
        effective_params = study.effective_params()
    except ValueError as exc:
        return ValidationResult(ok=False, problems=[str(exc)], study=study)

    try:
        parse_params(discovered.model, effective_params)
    except ParamsError as exc:
        problems.extend(exc.messages)

    return ValidationResult(ok=not problems, problems=problems, study=study)
