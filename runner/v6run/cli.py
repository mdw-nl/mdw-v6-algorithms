"""`v6run` CLI (AGENTS.md §9.4): `v6run validate study.yaml`, `v6run run study.yaml --out results/`."""

import argparse
import sys

from v6run.runstudy import RunnerError, run
from v6run.validate import validate


def _cmd_validate(args: argparse.Namespace) -> int:
    result = validate(args.study)
    if result.ok:
        print(f"OK: '{args.study}' is valid.")
        return 0
    print(f"Invalid study file '{args.study}':", file=sys.stderr)
    for problem in result.problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


def _cmd_run(args: argparse.Namespace) -> int:
    mfa_code = None
    if args.mfa:
        mfa_code = input("Two-factor authentication code (Enter to skip): ").strip() or None
    try:
        result = run(args.study, out_dir=args.out, wait_timeout_s=args.wait_timeout, mfa_code=mfa_code)
    except RunnerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Results written to {result.out_dir}")
    return 0 if result.envelope.get("status") != "error" else 1


def _cmd_list(_args: argparse.Namespace) -> int:
    print("`v6run list` is not implemented yet.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="v6run", description="Run studies against MDW's standard algorithms."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a study file without running it.")
    validate_parser.add_argument("study", help="Path to the study YAML file.")
    validate_parser.set_defaults(func=_cmd_validate)

    run_parser = subparsers.add_parser("run", help="Run a study against its profile's server.")
    run_parser.add_argument("study", help="Path to the study YAML file.")
    run_parser.add_argument("--out", default=None, help="Output directory (default: the study's 'output').")
    run_parser.add_argument(
        "--wait-timeout",
        type=float,
        default=600.0,
        help="Seconds to wait for the task to finish (default: 600).",
    )
    run_parser.add_argument(
        "--mfa",
        action="store_true",
        help="Prompt for a two-factor code before connecting (needed on servers with 2FA enabled).",
    )
    run_parser.set_defaults(func=_cmd_run)

    list_parser = subparsers.add_parser("list", help="(not implemented yet)")
    list_parser.set_defaults(func=_cmd_list)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
