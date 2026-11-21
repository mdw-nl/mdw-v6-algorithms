"""v6run: the researcher-facing CLI and Python API for running studies (AGENTS.md §9.4)."""

from v6run.runstudy import RunnerError, RunResult, run
from v6run.validate import ValidationResult, validate

__all__ = ["RunResult", "RunnerError", "ValidationResult", "run", "validate"]
