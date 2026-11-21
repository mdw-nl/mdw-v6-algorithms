"""Node + central result envelopes, error codes, and `safe_federated` (AGENTS.md §7.1).

Every federated function is wrapped with `safe_federated`. It never raises for data
problems: validation failures become scoped entries in the envelope's `errors` list
(so one bad column only knocks out that column, AGENTS.md §1.3/§7.1), and a genuine bug
becomes a scrubbed `INTERNAL_ERROR` entry instead of an unhandled exception reaching the
node's stdout with raw data values in it.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from v6core import provenance
from v6core._typing import AnyAlgorithmClient
from v6core.serialization import to_jsonsafe

logger = logging.getLogger(__name__)

ENVELOPE_VERSION = 1

# Extend these two sets in this module only (AGENTS.md §7.1).
NODE_ERROR_CODES = frozenset(
    {
        "INVALID_PARAM",
        "MISSING_COLUMN",
        "NON_NUMERIC",
        "NON_BINARY",
        "INVALID_VALUE",
        "EMPTY_AFTER_FILTER",
        "BELOW_MIN_ROWS",
        "BELOW_MIN_EVENTS",
        "SUPPRESSED",
        "NOT_SUBTASK",
        "INTERNAL_ERROR",
    }
)

CENTRAL_ERROR_CODES = frozenset(
    {
        "TIMEOUT",
        "NODE_FAILED",
        "NO_RESULT",
        "QUORUM_NOT_MET",
        "RANK_DEFICIENT",
        "SINGULAR_MATRIX",
        "NOT_CONVERGED",
        "NUMERICAL_FAILURE",
        "TOO_FEW_OBSERVATIONS",
        "INVALID_PARAM",
    }
)


@dataclass(frozen=True, slots=True)
class NodeError:
    """One entry of a node envelope's `errors` list."""

    code: str
    scope: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "scope": self.scope, "message": self.message}


class AlgorithmError(Exception):
    """Raise inside a `safe_federated`-wrapped function for an expected, scoped failure.

    Caught by `safe_federated` and turned into one `errors` entry with `status="error"`
    (the whole node result is unusable -- e.g. a malformed request). For a failure that
    should only take down *part* of the result (e.g. one bad column among several),
    return it as a `NodeError` in the function's own result instead of raising -- see
    the `descriptive_statistics` core module for an example.

    Never raise this for a bug. An uncaught exception already becomes a safe, scrubbed
    `INTERNAL_ERROR` entry; raising `AlgorithmError` is only for conditions the function
    itself recognizes and can describe without leaking data values.
    """

    def __init__(self, code: str, scope: str, message: str):
        if code not in NODE_ERROR_CODES:
            raise ValueError(f"Unknown node error code {code!r}; extend NODE_ERROR_CODES in envelope.py")
        super().__init__(message)
        self.code = code
        self.scope = scope
        self.message = message

    def to_node_error(self) -> NodeError:
        return NodeError(self.code, self.scope, self.message)


def node_envelope(
    *,
    status: str,
    organization_id: int | None,
    result: dict | None = None,
    errors: list[NodeError] | None = None,
) -> dict[str, Any]:
    """Build the JSON-safe node envelope described in AGENTS.md §7.1."""
    return to_jsonsafe(
        {
            "envelope_version": ENVELOPE_VERSION,
            "status": status,
            "organization_id": organization_id,
            "result": result or {},
            "errors": [e.to_dict() for e in (errors or [])],
        }
    )


FederatedOutcome = tuple[dict[str, Any], list[NodeError]]


def safe_federated(exempt_provenance: bool = False) -> Callable:
    """Decorator for a federated (node-side) function.

    The decorated function receives `(client, ...)` like any vantage6 federated
    function, and must return a `(result, errors)` tuple: `result` is the function's
    JSON-able payload (possibly partial), `errors` is a list of `NodeError` describing
    anything that went wrong but didn't take down the whole result.

    `safe_federated` then:
    - checks the provenance guard (`v6core.provenance`), unless `exempt_provenance=True`
      (e.g. a `data_check` function meant to be called directly)
    - catches `AlgorithmError` and turns it into a `status="error"` envelope
    - catches any other exception, logs it server-side, and returns a scrubbed
      `INTERNAL_ERROR` envelope that never echoes the exception text (AGENTS.md §7.1:
      pandas/numpy messages often quote individual values)
    - infers `status` from the returned `(result, errors)`: `"ok"` with no errors,
      `"partial"` if there's both a usable result and errors, `"error"` if the result
      is empty and there were errors

    Must be the innermost decorator, directly above the function -- `@data(...)` and
    `@algorithm_client` go outside it, exactly as vantage6 expects:

        @data(1)
        @algorithm_client
        @safe_federated()
        def compute_local_stats(client, df, statistics, filters=None): ...
    """

    def decorator(func: Callable[..., FederatedOutcome]) -> Callable[..., dict]:
        @wraps(func)
        def wrapper(client: AnyAlgorithmClient, *args: Any, **kwargs: Any) -> dict:
            organization_id = getattr(client, "organization_id", None)

            if not exempt_provenance:
                try:
                    provenance.ensure_spawned_by_central(client)
                except provenance.ProvenanceError as exc:
                    return node_envelope(
                        status="error",
                        organization_id=organization_id,
                        errors=[NodeError("NOT_SUBTASK", "node", str(exc))],
                    )

            try:
                result, errors = func(client, *args, **kwargs)
            except AlgorithmError as exc:
                return node_envelope(
                    status="error",
                    organization_id=organization_id,
                    errors=[exc.to_node_error()],
                )
            except Exception:
                logger.exception("Unhandled error in federated function %r", getattr(func, "__name__", func))
                return node_envelope(
                    status="error",
                    organization_id=organization_id,
                    errors=[
                        NodeError(
                            "INTERNAL_ERROR",
                            "node",
                            "An internal error occurred while processing this request.",
                        )
                    ],
                )

            if errors:
                status = "partial" if result else "error"
            else:
                status = "ok"
            return node_envelope(status=status, organization_id=organization_id, result=result, errors=errors)

        # Preserve the mock-client detection flags set by an inner safe_federated-
        # wrapped function, in case a caller ever stacks decorators unusually -- the
        # same dynamic-marker idiom `vantage6.algorithm.tools.decorators` itself uses,
        # which ty cannot type-check against a plain `Callable`.
        wrapper.wrapped_in_algorithm_client_decorator = getattr(  # ty: ignore[missing-attribute]
            func, "wrapped_in_algorithm_client_decorator", False
        )
        wrapper.wrapped_in_data_decorator = getattr(  # ty: ignore[missing-attribute]
            func, "wrapped_in_data_decorator", False
        )
        return wrapper

    return decorator


@dataclass(frozen=True, slots=True)
class CentralError:
    code: str
    scope: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "scope": self.scope, "message": self.message}


@dataclass(slots=True)
class CentralResult:
    """Accumulator for building the central envelope described in AGENTS.md §9.2."""

    algorithm_name: str
    algorithm_version: str
    v6core_version: str
    params: dict
    participation: list[dict] = field(default_factory=list)
    result: dict | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[CentralError] = field(default_factory=list)
    privacy: dict = field(default_factory=dict)
    status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        status = self.status
        if status is None:
            status = "error" if self.errors or self.result is None else ("partial" if self.warnings else "ok")
        return to_jsonsafe(
            {
                "status": status,
                "algorithm": {
                    "name": self.algorithm_name,
                    "version": self.algorithm_version,
                    "v6core_version": self.v6core_version,
                },
                "params": self.params,
                "participation": self.participation,
                "result": self.result,
                "warnings": self.warnings,
                "errors": [e.to_dict() for e in self.errors],
                "privacy": self.privacy,
            }
        )
