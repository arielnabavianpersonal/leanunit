from __future__ import annotations

import argparse
import datetime
import getpass
import json
import subprocess
import sys
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

from leanunit.approve import ApproveError, run_approve
from leanunit.check import run_check
from leanunit.config import ConfigError, load_config
from leanunit.fix import FixError, run_fix
from leanunit.guide import guide_text, write_guide
from leanunit.lean import LeanError
from leanunit.lock import LockError
from leanunit.pycode import TargetError
from leanunit.report import Report
from leanunit.scaffold import InitError, init_project
from leanunit.stubs import StubError, scaffold_target

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_NEEDS_HUMAN = 3


def main(argv: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    root = Path(options.root).resolve()
    try:
        return options.handler(root, options)
    except (ConfigError, LockError, ApproveError, FixError, InitError, StubError, TargetError) as error:
        print(f"leanunit: {error}", file=sys.stderr)
        return EXIT_USAGE
    except LeanError as error:
        print(f"leanunit: {error}\n{error.log}", file=sys.stderr)
        return EXIT_FAILED


def exit_code(report: Report) -> int:
    if report.passed:
        return EXIT_OK
    return EXIT_NEEDS_HUMAN if report.needs_human_only else EXIT_FAILED


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leanunit", description="Lean proofs instead of hand-written unit tests.")
    parser.add_argument("--root", default=".", help="the directory that contains leanunit.toml")
    parser.add_argument("--version", action="version", version=f"leanunit {_version()}")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="verify the laws, the proofs, the conformance, and the coverage")
    check.add_argument("--json", action="store_true", help="print the report as JSON")
    check.set_defaults(handler=_check)

    coverage = commands.add_parser("coverage", help="show the mirrors, the laws, and the executed lines of each target")
    coverage.add_argument("--json", action="store_true", help="print the coverage as JSON")
    coverage.set_defaults(handler=_coverage)

    new = commands.add_parser("new", help="write Lean types, generators, and mirror stubs for a Python target")
    new.add_argument("target", help="a module:Qualname target, for example pkg.module:MyClass")
    new.add_argument("--name", help="the name of the Lean modules, for example MyClass")
    new.set_defaults(handler=_new)

    approve = commands.add_parser("approve", help="record your approval of laws in leanunit.lock")
    approve.add_argument("names", nargs="*", help="full or short law names")
    approve.add_argument("--all", action="store_true", help="approve every current law and drop removed laws")
    approve.set_defaults(handler=_approve)

    fix = commands.add_parser("fix", help="start the configured agent on a failed check, then check again")
    fix.add_argument("--intent", help="tell the agent what you changed on purpose")
    fix.set_defaults(handler=_fix)

    guide = commands.add_parser("guide", help="show the guide for humans and agents")
    guide.add_argument("--write", action="store_true", help="write LEANUNIT.md and a pointer in AGENTS.md")
    guide.set_defaults(handler=_guide)

    init = commands.add_parser("init", help="make leanunit.toml, leanunit.lock, the Lean project, and LEANUNIT.md")
    init.add_argument("--source-root", default=".", help="the directory that Python imports the code from")
    init.add_argument("--cover", action="append", default=[], help="a module:Qualname target, more than once")
    init.set_defaults(handler=_init)
    return parser


def _check(root: Path, options: argparse.Namespace) -> int:
    report = run_check(load_config(root))
    print(report.to_json() if options.json else report.render(), end="\n" if options.json else "")
    return exit_code(report)


def _coverage(root: Path, options: argparse.Namespace) -> int:
    report = run_check(load_config(root))
    if not report.coverage:
        print(report.render(), end="")
        return EXIT_FAILED
    if options.json:
        print(json.dumps([entry.to_dict() for entry in report.coverage], indent=2))
    else:
        print(report.render_coverage(), end="")
    return EXIT_OK


def _new(root: Path, options: argparse.Namespace) -> int:
    result = scaffold_target(load_config(root), options.target, options.name)
    for path in result.created:
        print(f"created {path}")
    print(f"wrote stub mirrors for {len(result.mirrors)} functions in Model/{result.name}.lean")
    if not result.in_cover_list:
        print(f'next: add "{options.target}" to the cover list in leanunit.toml')
    print("next: run `leanunit check`. Each mismatch shows the real output of the code. See `leanunit guide`.")
    return EXIT_OK


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
    result = run_fix(load_config(root), intent=options.intent)
    if not result.started_agent:
        print(result.before.render(), end="")
        if result.before.needs_human_only:
            print("Nothing for an agent to do. The findings above need a human.")
        return exit_code(result.before)
    if result.agent_exit_code is None:
        print("The agent did not stop before the timeout.")
    for path in result.restored:
        print(f"restored {path}, because the agent must not change it")
    print(result.after.render(), end="")
    if result.diagnosis:
        print("\nAgent diagnosis:\n" + result.diagnosis)
    return exit_code(result.after)


def _guide(root: Path, options: argparse.Namespace) -> int:
    if not options.write:
        print(guide_text(), end="")
        return EXIT_OK
    written = write_guide(root)
    for path in written:
        print(f"wrote {path}")
    if not written:
        print("LEANUNIT.md and the pointers are up to date")
    return EXIT_OK


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


def _version() -> str:
    try:
        return metadata.version("leanunit")
    except metadata.PackageNotFoundError:
        return "unknown"
