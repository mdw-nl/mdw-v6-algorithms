"""Human-facing reporting (AGENTS.md §9.5): participation and warnings must be
prominent, and a `partial` result must never look like a clean one.

No plotting here (forest plots, KM curves, ROC/calibration): that's a documented,
deliberate gap for this first version of the runner, not an oversight -- see
`runner/README.md`.
"""

from pathlib import Path
from typing import Any


def _status_banner(status: str) -> str:
    return {
        "ok": "OK",
        "partial": "PARTIAL -- incomplete, read the warnings below",
        "error": "ERROR -- no usable result",
    }.get(status, status.upper())


def print_summary(envelope: dict[str, Any]) -> None:
    """Print status/participation/warnings prominently to stdout."""
    status = envelope.get("status", "unknown")
    print(f"\n=== Result: {_status_banner(status)} ===")

    algorithm = envelope.get("algorithm") or {}
    if algorithm:
        print(f"Algorithm: {algorithm.get('name')} v{algorithm.get('version')}")

    participation = envelope.get("participation") or []
    if participation:
        print("\nParticipation:")
        for entry in participation:
            reason = f" ({entry['reason']})" if entry.get("reason") else ""
            print(f"  - {entry['organization']}: {entry['status']}{reason}")

    errors = envelope.get("errors") or []
    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - [{error.get('code')}] {error.get('scope')}: {error.get('message')}")

    warnings = envelope.get("warnings") or []
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")

    print()


def write_summary_md(envelope: dict[str, Any], path: Path) -> None:
    status = envelope.get("status", "unknown")
    algorithm = envelope.get("algorithm") or {}
    lines = [
        f"# {algorithm.get('name', 'algorithm')} -- {_status_banner(status)}",
        "",
        f"- **version**: {algorithm.get('version', '?')}",
        f"- **v6core**: {algorithm.get('v6core_version', '?')}",
        f"- **status**: `{status}`",
        "",
    ]

    participation = envelope.get("participation") or []
    if participation:
        lines += ["## Participation", "", "| Organization | Status | Reason |", "|---|---|---|"]
        lines += [f"| {p['organization']} | {p['status']} | {p.get('reason', '')} |" for p in participation]
        lines.append("")

    errors = envelope.get("errors") or []
    if errors:
        lines += ["## Errors", ""]
        lines += [f"- `[{e.get('code')}]` {e.get('scope')}: {e.get('message')}" for e in errors]
        lines.append("")

    warnings = envelope.get("warnings") or []
    if warnings:
        lines += ["## Warnings", ""]
        lines += [f"- {w}" for w in warnings]
        lines.append("")

    privacy = envelope.get("privacy") or {}
    if privacy:
        lines += ["## Privacy", "", f"```\n{privacy}\n```", ""]

    result = envelope.get("result")
    if result is not None:
        lines += ["## Result", "", "See `result.json` for the full envelope."]

    path.write_text("\n".join(lines))
