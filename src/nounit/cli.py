from __future__ import annotations

import argparse
import datetime
import getpass
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from nounit.approve import ApproveError, run_approve
from nounit.check import run_check
from nounit.config import ConfigError, load_config
from nounit.fix import FixError, run_fix
from nounit.lean import LeanError
from nounit.lock import LockError
from nounit.report import Owner
from nounit.scaffold import InitError, init_project

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def main(argv: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    root = Path(options.root).resolve()
    try:
        return options.handler(root, options)
    except (ConfigError, LockError, ApproveError, FixError, InitError) as error:
        print(f"nounit: {error}", file=sys.stderr)
        return EXIT_USAGE
    except LeanError as error:
        print(f"nounit: {error}\n{error.log}", file=sys.stderr)
        return EXIT_FAILED


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nounit", description="Lean proofs instead of hand-written unit tests.")
    parser.add_argument("--root", default=".", help="the directory that contains nounit.toml")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="verify the laws, the proofs, and the conformance of the models")
    check.add_argument("--json", action="store_true", help="print the report as JSON")
    check.set_defaults(handler=_check)

    approve = commands.add_parser("approve", help="record your approval of laws in nounit.lock")
    approve.add_argument("names", nargs="*", help="full or short law names")
    approve.add_argument("--all", action="store_true", help="approve every current law and drop removed laws")
    approve.set_defaults(handler=_approve)

    fix = commands.add_parser("fix", help="start the agent on a failed check, then check again")
    fix.set_defaults(handler=_fix)

    init = commands.add_parser("init", help="make nounit.toml, nounit.lock, and the Lean project")
    init.add_argument("--source-root", default=".", help="the directory that Python imports the code from")
    init.add_argument("--cover", action="append", default=[], help="a module:Qualname target, more than once")
    init.set_defaults(handler=_init)
    return parser


def _check(root: Path, options: argparse.Namespace) -> int:
    report = run_check(load_config(root))
    print(report.to_json() if options.json else report.render(), end="" if not options.json else "\n")
    return EXIT_OK if report.passed else EXIT_FAILED


def _approve(root: Path, options: argparse.Namespace) -> int:
    result = run_approve(
        load_config(root),
        names=options.names,
        approve_all=options.all,
        approver=_approver(root),
        today=datetime.date.today().isoformat(),
    )
    for name in result.approved:
        print(f"approved {name}")
    for name in result.removed:
        print(f"removed {name}")
    print(f"wrote {result.lock_path}")
    return EXIT_OK


def _fix(root: Path, options: argparse.Namespace) -> int:
    result = run_fix(load_config(root))
    if not result.started_agent:
        print(result.before.render(), end="")
        human = result.before.owned_by(Owner.HUMAN)
        print("Nothing for the agent to do." + (" The findings above need a human." if human else ""))
        return EXIT_OK if result.before.passed else EXIT_FAILED
    if result.agent_exit_code is None:
        print("The agent did not stop before the timeout.")
    for path in result.restored:
        print(f"restored {path}, because the agent must not change it")
    print(result.after.render(), end="")
    if result.diagnosis:
        print("\nAgent diagnosis:\n" + result.diagnosis)
    return EXIT_OK if result.after.passed else EXIT_FAILED


def _init(root: Path, options: argparse.Namespace) -> int:
    result = init_project(root, options.source_root, tuple(options.cover))
    for path in result.created:
        print(f"created {path}")
    return EXIT_OK


def _approver(root: Path) -> str:
    try:
        email = subprocess.run(
            ["git", "config", "user.email"], cwd=root, capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        email = ""
    return email or getpass.getuser()
