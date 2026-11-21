"""Guard that a federated function was spawned as a subtask by `central()` (AGENTS.md §8.4).

Without this guard, someone could call a federated (node-side) function directly with
loosened privacy settings and get traceable output -- the node has no way to tell a
request from `central()` apart from one aimed straight at it. The check relies on
vantage6 internals (the container token, the task's `parent` field), which is why it
lives in this one place and is re-verified on every vantage6 upgrade (AGENTS.md §5).

The mock-client exemption lives here, and only here (AGENTS.md §8.4): the
`MockAlgorithmClient` used in unit tests has no real parent task to check.
"""

import logging

from v6core._typing import AnyAlgorithmClient

logger = logging.getLogger(__name__)


class ProvenanceError(Exception):
    """A federated function was invoked other than as a subtask of `central()`."""


def ensure_spawned_by_central(client: AnyAlgorithmClient) -> None:
    """Raise `ProvenanceError` unless `client` belongs to a task with a parent.

    Skipped for `MockAlgorithmClient` (in-process tests): see module docstring.
    Any other client with no decodable container token, or whose parent task
    cannot be looked up, fails closed (raises `ProvenanceError`) rather than
    silently allowing the call.
    """
    from vantage6.algorithm.tools.mock_client import MockAlgorithmClient

    if isinstance(client, MockAlgorithmClient):
        logger.info("Skipping parent-task guard: MockAlgorithmClient detected.")
        return

    token = getattr(client, "_access_token", None)
    if token is None:
        raise ProvenanceError(
            "No access token found on the client; cannot verify this call was spawned by central()."
        )

    try:
        import jwt

        payload = jwt.decode(token, options={"verify_signature": False})
        task_id = payload["sub"]["task_id"]
    except Exception as exc:
        raise ProvenanceError("Could not decode the task identity from the container token.") from exc

    try:
        task = client.task.get(task_id)
    except Exception as exc:
        raise ProvenanceError(f"Could not look up task {task_id} to verify its parent task.") from exc

    if not isinstance(task, dict) or not task.get("parent"):
        raise ProvenanceError(
            "This function may only be invoked as a subtask created by this image's "
            "central() function; direct invocation is not permitted."
        )
