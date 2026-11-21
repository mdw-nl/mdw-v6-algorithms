"""Run a study against a live vantage6 server (AGENTS.md §9.4/§9.5).

`client.wait_for_results()` (and the lower-level `wait_for_task_completion` it calls)
polls forever -- the same hazard `v6core.orchestration.fan_out` exists to avoid on the
node side. `_wait_for_task` here polls the same `task/{id}/status` endpoint directly,
against an explicit deadline, instead.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from vantage6.client import Client
from vantage6.common.task_status import TaskStatus, has_task_finished

from v6run.profiles import resolve_profile
from v6run.reporting import print_summary, write_summary_md
from v6run.study import Study
from v6run.validate import validate

POLL_INTERVAL_S = 2.0
DEFAULT_WAIT_TIMEOUT_S = 600.0


class RunnerError(Exception):
    """A study could not be run -- invalid study, organization not found, timeout, ..."""


@dataclass(frozen=True, slots=True)
class RunResult:
    study: Study
    task_id: int
    envelope: dict
    out_dir: Path


class _RequestClient(Protocol):
    """The one method `_wait_for_task` needs -- narrower than `vantage6.client.Client`
    so a test double doesn't have to stand in for the whole thing. Positional-only
    (`/`): the real client names this parameter `endpoint`; we only ever call it
    positionally, so the name shouldn't matter structurally."""

    def request(self, path: str, /) -> dict: ...


def _wait_for_task(client: _RequestClient, task_id: int, timeout_s: float) -> TaskStatus:
    deadline = time.monotonic() + timeout_s
    while True:
        # The server hands back the status as its plain string value (JSON has no
        # enum type); TaskStatus is a `str` Enum, so it compares equal to that string.
        status = cast(TaskStatus, client.request(f"task/{task_id}/status").get("status"))
        if has_task_finished(status):
            return status
        if time.monotonic() >= deadline:
            raise RunnerError(f"Task {task_id} did not finish within {timeout_s}s (last status: '{status}').")
        time.sleep(min(POLL_INTERVAL_S, max(0.0, deadline - time.monotonic())))


def _lookup_id(items: list[dict], name: str, kind: str) -> int:
    match = next((item for item in items if item["name"] == name), None)
    if match is None:
        available = sorted(item["name"] for item in items)
        raise RunnerError(f"{kind} '{name}' not found; available: {available}")
    return match["id"]


class _EncryptionClient(Protocol):
    """Narrower than `vantage6.client.Client` so a test double only has to implement
    this one method, not the whole real client. Positional-only (`/`): we only ever
    call this positionally, so a test double's parameter name shouldn't matter
    structurally."""

    def setup_encryption(self, private_key_file: str | None, /) -> None: ...


def _setup_encryption(client: _EncryptionClient, private_key_path: str | None) -> None:
    """Enable real end-to-end encryption when the profile names an existing key.

    `client.setup_encryption(None)` (a no-op "dummy" encryptor) only works on an
    *unencrypted* collaboration -- a real, encryption-enforcing server rejects it
    outright ("Your collaboration requires encryption, but input is not encrypted!").

    This deliberately never generates a new key: vantage6 encryption keys are
    per-organization, shared with the node, so `private_key_path` must point at the
    SAME private key file the organization's own node already uses. Reusing it means
    `setup_encryption()` finds a match already registered on the server and uploads
    nothing. Generating a different key here instead would overwrite the
    organization's registered public key and break the node's own ability to decrypt
    tasks until its config is updated to match -- so a missing path fails loudly here
    rather than silently falling through to a fresh keypair.
    """
    if private_key_path is None:
        client.setup_encryption(None)
        return
    path = Path(private_key_path)
    if not path.exists():
        raise RunnerError(
            f"Profile's private_key_path ({path}) does not exist. This must be the "
            "organization's existing node private key -- see runner/README.md."
        )
    client.setup_encryption(str(path))


def run(
    study_path: str,
    out_dir: str | None = None,
    wait_timeout_s: float = DEFAULT_WAIT_TIMEOUT_S,
    mfa_code: str | None = None,
) -> RunResult:
    """Validate, then run `study_path` against its profile's server; write results.

    Raises `RunnerError` for anything that should stop the run cleanly (invalid study,
    unknown organization, a task that never finishes). Never silently hangs: the wait
    for task completion is bounded by `wait_timeout_s`, independent of any
    algorithm-internal `timeout_s` the request itself carries.
    """
    validation = validate(study_path)
    if not validation.ok or validation.study is None:
        raise RunnerError("Invalid study file:\n" + "\n".join(f"  - {p}" for p in validation.problems))
    study = validation.study

    profile = resolve_profile(study.profile)
    client = Client(profile.server_url, profile.port, profile.api_path, log_level="warn")
    # Upstream types `mfa_code` as `int | str` despite defaulting to (and genuinely
    # accepting) `None` for an account without 2FA enabled -- an inaccurate annotation,
    # not a real constraint.
    client.authenticate(profile.username, profile.password, mfa_code=cast(Any, mfa_code))
    _setup_encryption(client, profile.private_key_path)

    collaborations = client.collaboration.list()["data"]
    collaboration_id = _lookup_id(collaborations, study.collaboration, "Collaboration")
    client.setup_collaboration(collaboration_id)

    organizations = client.organization.list()["data"]
    initiating_org_id = _lookup_id(organizations, study.initiating_org, "Organization")

    image = study.image or f"{study.algorithm}:{study.version}"

    try:
        kwargs = study.effective_params()
    except ValueError as exc:
        raise RunnerError(str(exc)) from exc

    task = client.task.create(
        collaboration=collaboration_id,
        organizations=[initiating_org_id],
        name=f"{study.algorithm} ({study.version})",
        description=f"v6run study: {study_path}",
        image=image,
        input_={"method": "central", "kwargs": kwargs},
        databases=[{"label": profile.database_label}],
    )
    task_id = task["id"]
    print(f"Task created (id={task_id}, image={image}); waiting up to {wait_timeout_s:.0f}s...")

    _wait_for_task(client, task_id, wait_timeout_s)

    results = client.result.from_task(task_id)
    items = results.get("data", []) if isinstance(results, dict) else results
    if not items:
        raise RunnerError(f"Task {task_id} finished but returned no results.")

    raw_result = items[0].get("result") if isinstance(items[0], dict) else items[0]
    if not raw_result:
        raise RunnerError(
            f"Task {task_id} finished but its result was empty (the algorithm may have crashed)."
        )
    envelope: dict[str, Any] = json.loads(raw_result) if isinstance(raw_result, str) else raw_result

    resolved_out_dir = Path(out_dir or study.output)
    resolved_out_dir.mkdir(parents=True, exist_ok=True)
    (resolved_out_dir / "result.json").write_text(json.dumps(envelope, indent=2))
    (resolved_out_dir / "params.json").write_text(json.dumps(study.params, indent=2))

    write_summary_md(envelope, resolved_out_dir / "summary.md")
    print_summary(envelope)

    return RunResult(study=study, task_id=task_id, envelope=envelope, out_dir=resolved_out_dir)
