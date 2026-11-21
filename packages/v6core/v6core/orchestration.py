"""Fan-out with a real timeout, never a bare `wait_for_results()` (AGENTS.md §7.2).

`client.wait_for_results()` polls forever -- an organization that's registered in the
collaboration but has no node running then hangs the whole run. `fan_out()` instead
creates the subtask(s) itself and polls `client.run.from_task()` against a deadline,
converting a timeout, a crashed run, a missing result or a malformed envelope into an
`Outcome` instead of letting any of them raise or hang.

Results are matched to organizations through each run's own `organization.id` and
`results.id`, never by list position (AGENTS.md §7.2).
"""

import time
from dataclasses import dataclass
from typing import Any, cast

from vantage6.common.task_status import TaskStatus, has_task_failed, has_task_finished

from v6core._typing import AnyAlgorithmClient

POLL_INTERVAL_S = 2.0


@dataclass(frozen=True, slots=True)
class Outcome:
    status: str  # "ok" | "error" | "timeout"
    envelope: dict | None = None
    reason: str | None = None


def fan_out(
    client: AnyAlgorithmClient,
    *,
    method: str,
    organizations: list[int],
    kwargs: dict | None = None,
    per_org_kwargs: dict[int, dict] | None = None,
    timeout_s: float = 300.0,
    name: str = "subtask",
    description: str | None = None,
) -> dict[int, Outcome]:
    """Fan a federated call out to `organizations` and collect their outcomes.

    - `kwargs` is sent to every organization when `per_org_kwargs` is not given (one
      task, one input, shared across organizations -- a single vantage6 task supports
      exactly this).
    - `per_org_kwargs` gives each organization different kwargs (merged on top of
      `kwargs`), which vantage6 can only do with one task per organization -- so this
      creates every task first, then polls all of them concurrently.

    Returns `{organization_id: Outcome}` for every id in `organizations`, regardless of
    whether its task ever finishes.
    """
    kwargs = kwargs or {}
    per_org_kwargs = per_org_kwargs or {}
    description = description or name

    outcomes: dict[int, Outcome] = {}
    task_id_by_org: dict[int, int] = {}

    if per_org_kwargs:
        for org_id in organizations:
            merged = {**kwargs, **per_org_kwargs.get(org_id, {})}
            try:
                task = client.task.create(
                    input_={"method": method, "kwargs": merged},
                    organizations=[org_id],
                    name=name,
                    description=description,
                )
                task_id_by_org[org_id] = _task_id(task)
            except Exception as exc:
                outcomes[org_id] = Outcome(status="error", reason=f"Could not create subtask: {exc}")
    else:
        try:
            task = client.task.create(
                input_={"method": method, "kwargs": kwargs},
                organizations=list(organizations),
                name=name,
                description=description,
            )
            for org_id in organizations:
                task_id_by_org[org_id] = _task_id(task)
        except Exception as exc:
            for org_id in organizations:
                outcomes[org_id] = Outcome(status="error", reason=f"Could not create subtask: {exc}")

    # Tracked per *organization*, not per task: when kwargs are shared, several
    # organizations' runs live under the same task id (AGENTS.md §7.2), and one
    # organization with no node running must never hold up -- or time out -- the
    # others sharing that task. Each run is collected the moment it finishes; only
    # the organizations still pending when the deadline passes are timed out.
    pending_org_ids = {org_id for org_id in task_id_by_org if org_id not in outcomes}
    deadline = time.monotonic() + timeout_s

    while pending_org_ids and time.monotonic() < deadline:
        task_ids_to_poll = {task_id_by_org[org_id] for org_id in pending_org_ids}
        newly_resolved: set[int] = set()
        for task_id in task_ids_to_poll:
            for run in client.run.from_task(task_id):
                org_id = _organization_id_of(run)
                if org_id is None or org_id not in pending_org_ids:
                    continue
                if has_task_finished(_run_status(run)):
                    outcomes[org_id] = _outcome_from_run(client, run)
                    newly_resolved.add(org_id)
        pending_org_ids -= newly_resolved
        if pending_org_ids:
            time.sleep(min(POLL_INTERVAL_S, max(0.0, deadline - time.monotonic())))

    for org_id in pending_org_ids:
        outcomes[org_id] = Outcome(status="timeout", reason=f"No result within {timeout_s}s")

    return outcomes


def _task_id(task: dict | int) -> int:
    # `MockAlgorithmClient.Task.create` is annotated `-> int` upstream even though it
    # returns the same dict shape as the real client (see v6core._typing); this only
    # narrows the static type back to what both clients actually return at runtime.
    return cast(dict, task)["id"]


def _organization_id_of(run: dict) -> int | None:
    org = run.get("organization")
    if isinstance(org, dict):
        return org.get("id")
    return None


def _run_status(run: dict) -> TaskStatus:
    # The server/mock client hand back the status as its plain string value (JSON has
    # no enum type); TaskStatus is a `str` Enum, so it compares equal to that string.
    return cast(TaskStatus, run.get("status", ""))


def _outcome_from_run(client: AnyAlgorithmClient, run: dict) -> Outcome:
    status = _run_status(run)
    if has_task_failed(status):
        return Outcome(status="error", reason=f"Node run ended with status '{status}'")

    results_ref = run.get("results")
    result_id = results_ref.get("id") if isinstance(results_ref, dict) else None
    if result_id is None:
        return Outcome(status="error", reason="Completed run carries no result reference")

    envelope: Any = client.result.get(result_id)
    if not isinstance(envelope, dict) or "status" not in envelope:
        return Outcome(status="error", reason="Malformed envelope returned by node")

    return Outcome(status="ok", envelope=envelope)
