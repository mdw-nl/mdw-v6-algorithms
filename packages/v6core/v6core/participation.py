"""Organization selection, min_rows/min_events exclusion, and quorum (AGENTS.md §3.2).

Replaces the ~25-line block that used to be copied into every `central()`.
"""

from dataclasses import dataclass

from v6core.envelope import CentralError


class ParticipationError(Exception):
    """A request-level participation problem (bad org names, quorum not met)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_central_error(self) -> CentralError:
        return CentralError(self.code, "node", self.message)


def select_organizations(all_orgs: list[dict], organizations: list[str] | None) -> list[dict]:
    """Restrict `all_orgs` (from `client.organization.list()`) to the named ones.

    `organizations=None` (the default) means every organization in the collaboration.
    Naming organizations lets a caller exclude one that's registered in the
    collaboration but has no node actually running -- without that, a subtask sent to
    it would simply never return (see `v6core.orchestration.fan_out`'s `timeout_s`,
    which is the other half of this: `organizations` narrows the fan-out before any
    task is created at all).
    """
    if organizations is None:
        return all_orgs
    if not organizations:
        raise ParticipationError(
            "INVALID_PARAM",
            "'organizations' was given as an empty list; omit it (or pass null) to use "
            "every organization in the collaboration, or list at least one organization name",
        )
    available = {org["name"] for org in all_orgs}
    missing = [name for name in organizations if name not in available]
    if missing:
        raise ParticipationError(
            "INVALID_PARAM",
            f"organization(s) {missing} not found in the collaboration; "
            f"available organizations: {sorted(available)}",
        )
    selected = set(organizations)
    return [org for org in all_orgs if org["name"] in selected]


@dataclass(frozen=True, slots=True)
class Participant:
    organization: str
    status: str  # "included" | "excluded" | "failed"
    reason: str | None = None

    def to_dict(self) -> dict:
        entry = {"organization": self.organization, "status": self.status}
        if self.reason is not None:
            entry["reason"] = self.reason
        return entry


def apply_min_floor(
    counts_by_org: dict[int, int | None], minimum: int, *, reason: str
) -> tuple[list[int], dict[int, str]]:
    """Split organizations by whether their reported count clears `minimum`.

    `counts_by_org` maps organization_id to a row/event count, or `None` when the
    count itself was suppressed or missing (treated as failing the floor -- a
    suppressed count can't be trusted to clear it). Returns
    `(qualifying_org_ids, {excluded_org_id: reason})`.
    """
    qualifying: list[int] = []
    excluded: dict[int, str] = {}
    for org_id, count in counts_by_org.items():
        if count is None or count < minimum:
            excluded[org_id] = reason
        else:
            qualifying.append(org_id)
    return qualifying, excluded


def check_quorum(n_included: int, min_organizations: int) -> None:
    """Raise `ParticipationError(QUORUM_NOT_MET)` if fewer than `min_organizations` qualify."""
    if n_included < min_organizations:
        raise ParticipationError(
            "QUORUM_NOT_MET",
            f"Only {n_included} organization(s) qualify, but 'min_organizations' requires "
            f"at least {min_organizations}.",
        )
