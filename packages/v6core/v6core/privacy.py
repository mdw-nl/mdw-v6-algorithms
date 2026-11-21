"""Privacy thresholds: safe defaults, absolute minimums, suppression (AGENTS.md §8.4)."""

import logging
from dataclasses import dataclass
from hashlib import blake2b
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PrivacyThresholds:
    """Defaults match the legacy code's values (AGENTS.md §8.4): cell count 5, min_events 10."""

    min_cell_count: int = 5
    min_rows: int = 5
    min_events: int = 10
    min_rows_per_parameter: int = 10
    min_events_per_parameter: int = 10
    max_categories: int = 20


DEFAULTS = PrivacyThresholds()

# Not configurable below these. A request under one is rejected with INVALID_PARAM
# (AGENTS.md §8.4) -- this stops settings like 0 or 1 that would make output traceable.
ABSOLUTE_MINIMUMS: dict[str, int] = {
    "min_cell_count": 3,
    "min_rows": 5,
    "min_events": 5,
    "min_rows_per_parameter": 1,
    "min_events_per_parameter": 1,
    "max_categories": 2,
}


class PrivacyParamError(Exception):
    """A requested threshold is below its absolute minimum."""


def resolve_threshold(name: str, requested: int | None) -> tuple[int, bool]:
    """Resolve one threshold by name.

    Returns `(effective_value, below_default)`. Raises `PrivacyParamError` if
    `requested` is below `ABSOLUTE_MINIMUMS[name]`. `requested=None` uses the default
    (never flagged as `below_default`, since nothing was lowered).
    """
    default = getattr(DEFAULTS, name)
    minimum = ABSOLUTE_MINIMUMS[name]
    value = default if requested is None else requested
    if value < minimum:
        raise PrivacyParamError(f"'{name}' must be >= {minimum} (absolute minimum), got {value}")
    return value, requested is not None and value < default


def suppressed_count(value: int, threshold: int) -> dict[str, Any]:
    """The standard shape for a count that may be suppressed (AGENTS.md §9.2)."""
    if value < threshold:
        return {"value": None, "suppressed": True}
    return {"value": value}


def data_fingerprint(df: pd.DataFrame) -> str:
    """A short hash of `df`'s shape and column names -- never its values or any request field.

    Used to seed *optional* secondary suppression / deterministic noise (AGENTS.md
    §8.4): "a hash of the node's own dataset (never a key from the request)". Because
    it depends only on the node's own data, two different requests against the same
    dataset pick the same secondary cell to perturb -- which is the point (an attacker
    diffing two releases can't use a changed key to undo it) -- while never being
    something a requester could choose or predict.
    """
    payload = repr(sorted(df.columns.astype(str).tolist())) + f":{len(df)}"
    return blake2b(payload.encode(), digest_size=8).hexdigest()


def deterministic_pick(fingerprint: str, *parts: str, modulus: int) -> int:
    """A deterministic index in `range(modulus)`, seeded by `fingerprint` and `parts`."""
    digest = blake2b(":".join((fingerprint, *parts)).encode(), digest_size=4).digest()
    return int.from_bytes(digest, "little") % modulus


def safe_log(level: str, message: str) -> None:
    """Log `message` at `level`. Callers must not interpolate raw data values into it --
    this just centralizes the call so a future redaction policy has one place to change.
    """
    getattr(logger, level)(message)
