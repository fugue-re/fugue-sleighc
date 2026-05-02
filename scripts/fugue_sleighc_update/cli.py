import argparse
from pathlib import Path

from . import agent, importer
from .log import die, status


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPO_ROOT / ".update-ghidra-report.txt"


def _next_steps(branch: str) -> str:
    return (
        f"\nNext steps:\n"
        f"  1. Review the resulting diff in vendored/CMakeLists.txt\n"
        f"  2. Inside vendored/ (this will be a root commit on an orphan branch):\n"
        f"       git commit -m \"support for Ghidra v{branch.removeprefix('ghidra-v')}\"\n"
        f"       git push -u origin {branch}\n"
        f"  3. In the outer repo:\n"
        f"       git add vendored Cargo.toml .gitmodules\n"
        f"       git commit -m \"support for Ghidra v{branch.removeprefix('ghidra-v')}\"\n"
    )


def cmd_import(args: argparse.Namespace) -> int:
    report, _ = importer.import_release(REPO_ROOT, args.version)
    status(f"import complete; run `fugue-sleighc-update reconcile` next")
    print(_next_steps(report.version.branch))
    return 0


def cmd_reconcile(_args: argparse.Namespace) -> int:
    if not REPORT_PATH.exists():
        die(f"missing {REPORT_PATH.name}; run `fugue-sleighc-update import` first")
    return agent.reconcile(REPO_ROOT, REPORT_PATH.read_text())


def cmd_update(args: argparse.Namespace) -> int:
    report, _ = importer.import_release(REPO_ROOT, args.version)
    rc = agent.reconcile(REPO_ROOT, REPORT_PATH.read_text())
    if rc == 0:
        print(_next_steps(report.version.branch))
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fugue-sleighc-update")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_import = sub.add_parser("import", help="import a Ghidra release into vendored/")
    p_import.add_argument("version", nargs="?", default=None,
                          help="version (e.g. 12.1) or tag (Ghidra_12.1_build); default: latest release")
    p_import.set_defaults(func=cmd_import)

    p_reconcile = sub.add_parser(
        "reconcile",
        help="run the agent to reconcile vendored/CMakeLists.txt against vendored/src/",
    )
    p_reconcile.set_defaults(func=cmd_reconcile)

    p_update = sub.add_parser("update", help="import + reconcile (end-to-end)")
    p_update.add_argument("version", nargs="?", default=None,
                          help="version (e.g. 12.1) or tag; default: latest release")
    p_update.set_defaults(func=cmd_update)

    args = parser.parse_args(argv)
    return args.func(args)
