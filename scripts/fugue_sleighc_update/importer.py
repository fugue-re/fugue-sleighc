import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .log import status, die

GHIDRA_REPO = "https://github.com/NationalSecurityAgency/ghidra.git"
GHIDRA_RELEASES_API = (
    "https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/latest"
)
GHIDRA_CPP_SUBPATH = "Ghidra/Features/Decompiler/src/decompile/cpp"
SOURCE_EXTENSIONS = (".cc", ".hh", ".h", ".y", ".l")
EXTRA_FILES = ("Doxyfile", "Makefile")


@dataclass(frozen=True)
class Version:
    tag: str
    short: str
    branch: str


def resolve_latest_tag() -> str:
    with urllib.request.urlopen(GHIDRA_RELEASES_API, timeout=30) as resp:
        data = json.load(resp)
    tag = data.get("tag_name")
    if not tag:
        die(f"could not resolve latest Ghidra tag from {GHIDRA_RELEASES_API}")
    return tag


def parse_version(raw: str) -> Version:
    if m := re.fullmatch(r"Ghidra_(.+)_build", raw):
        short = m.group(1)
        return Version(tag=raw, short=short, branch=f"ghidra-v{short}")
    if m := re.fullmatch(r"ghidra-v(.+)", raw):
        short = m.group(1)
        return Version(tag=f"Ghidra_{short}_build", short=short, branch=raw)
    if re.fullmatch(r"\d+(?:\.\d+)+", raw):
        return Version(tag=f"Ghidra_{raw}_build", short=raw, branch=f"ghidra-v{raw}")
    die(f"unrecognized version format: '{raw}' (expected e.g. 12.1 or Ghidra_12.1_build)")


def git(args: list[str], cwd: Path | None = None, check: bool = True,
        capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
    )


def vendored_dirty(repo_root: Path) -> bool:
    out = git(["status", "--porcelain"], cwd=repo_root / "vendored", capture=True).stdout
    return bool(out.strip())


def outer_path_dirty(repo_root: Path, path: str) -> bool:
    return git(["diff", "--quiet", "--", path], cwd=repo_root, check=False).returncode != 0


def branch_exists_local(vendored: Path, branch: str) -> bool:
    return git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=vendored, check=False,
    ).returncode == 0


def branch_exists_origin(vendored: Path, branch: str) -> bool:
    return git(
        ["ls-remote", "--exit-code", "--heads", "origin", branch],
        cwd=vendored, check=False, capture=True,
    ).returncode == 0


def shallow_clone(tag: str, dest: Path) -> None:
    status(f"shallow-cloning {tag} into {dest}")
    git([
        "clone", "--depth", "1", "--branch", tag, "--single-branch",
        GHIDRA_REPO, str(dest),
    ])


def list_dir(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    return sorted(p.name for p in path.iterdir() if p.is_file())


def copy_sources(ghidra_cpp: Path, dest: Path) -> int:
    copied = 0
    for child in ghidra_cpp.iterdir():
        if not child.is_file():
            continue
        if child.suffix in SOURCE_EXTENSIONS or child.name in EXTRA_FILES:
            shutil.copy2(child, dest / child.name)
            copied += 1
    return copied


def update_flake_version(flake_nix: Path, new_version: str) -> None:
    text = flake_nix.read_text()
    new_text = re.sub(
        r'(version\s*=\s*")[^"]+(";)',
        rf'\g<1>{new_version}\g<2>',
        text,
    )
    if new_text != text:
        flake_nix.write_text(new_text)


def bump_cargo_version(cargo_toml: Path, new_ghidra_version: str) -> str:
    text = cargo_toml.read_text()
    m = re.search(
        r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)\+[^"]+"',
        text,
        re.MULTILINE,
    )
    if not m:
        die("could not parse version line in Cargo.toml")
    major, minor, patch = int(m[1]), int(m[2]), int(m[3])
    new_value = f'version = "{major}.{minor}.{patch + 1}+{new_ghidra_version}"'
    cargo_toml.write_text(
        re.sub(r'^version\s*=\s*"[^"]+"', new_value, text, count=1, flags=re.MULTILINE)
    )
    return f"{major}.{minor}.{patch + 1}+{new_ghidra_version}"


def stale_cmake_refs(cmake_path: Path, vendored: Path) -> list[str]:
    if not cmake_path.exists():
        return []
    refs = sorted(set(re.findall(
        r"src/[A-Za-z0-9_./-]+\.(?:cc|hh|h|y|l)",
        cmake_path.read_text(),
    )))
    return [r for r in refs if not (vendored / r).exists()]


@dataclass
class ImportReport:
    version: Version
    before: list[str]
    after: list[str]

    @property
    def added(self) -> list[str]:
        return sorted(set(self.after) - set(self.before))

    @property
    def removed(self) -> list[str]:
        return sorted(set(self.before) - set(self.after))

    @property
    def new_grammar_lexer(self) -> list[str]:
        return [f for f in self.added if f.endswith((".y", ".l"))]

    def render(self, stale_refs: list[str]) -> str:
        def block(title: str, items: list[str], placeholder: str = "") -> str:
            if not items:
                return f"{title}:\n  {placeholder}\n" if placeholder else f"{title}:\n"
            body = "\n".join(f"  {x}" for x in items)
            return f"{title}:\n{body}\n"

        return (
            f"Ghidra import report\n"
            f"Tag:     {self.version.tag}\n"
            f"Version: {self.version.short}\n"
            f"Branch:  {self.version.branch}\n\n"
            f"File counts:\n"
            f"  before: {len(self.before)} files\n"
            f"  after:  {len(self.after)} files\n\n"
            + block("Added (in new, not in previous)", self.added)
            + "\n"
            + block("Removed (in previous, not in new)", self.removed)
            + "\n"
            + block(
                "New grammar/lexer files (likely need BISON_TARGET / FLEX_TARGET)",
                self.new_grammar_lexer,
                "(none)",
            )
            + "\n"
            + block("CMakeLists.txt references that no longer exist", stale_refs)
        )


def import_release(repo_root: Path, version_arg: str | None) -> tuple[ImportReport, Path]:
    if version_arg:
        version = parse_version(version_arg)
    else:
        status("no version given, querying upstream for latest release")
        version = parse_version(resolve_latest_tag())

    status(f"Ghidra tag:   {version.tag}")
    status(f"version:      {version.short}")
    status(f"branch:       {version.branch}")

    vendored = repo_root / "vendored"
    if not (repo_root / ".gitmodules").is_file():
        die("must be run from the fugue-sleighc repo root")
    if not (vendored / ".git").exists():
        die("vendored/ submodule not initialized; run 'git submodule update --init'")
    if vendored_dirty(repo_root):
        die("vendored/ has uncommitted changes; commit or stash them first")
    for f in (".gitmodules", "Cargo.toml"):
        if outer_path_dirty(repo_root, f):
            die(f"outer repo has unstaged changes to {f}; commit or stash first")
    if branch_exists_local(vendored, version.branch):
        die(f"branch '{version.branch}' already exists locally in vendored/; nothing to do")
    if branch_exists_origin(vendored, version.branch):
        die(f"branch '{version.branch}' already exists on origin in vendored/; check out and update manually")

    before = list_dir(vendored / "src")

    with tempfile.TemporaryDirectory(prefix="fugue-sleighc-ghidra.") as tmp:
        ghidra = Path(tmp) / "ghidra"
        shallow_clone(version.tag, ghidra)
        ghidra_cpp = ghidra / GHIDRA_CPP_SUBPATH
        if not ghidra_cpp.is_dir():
            die(f"expected {ghidra_cpp} to exist in clone")

        status(f"creating orphan branch {version.branch} in vendored/")
        git(["checkout", "--orphan", version.branch], cwd=vendored)

        status(f"replacing vendored/src/ with files from {version.tag}")
        src_dir = vendored / "src"
        if src_dir.exists():
            shutil.rmtree(src_dir)
        src_dir.mkdir(parents=True)

        copied = copy_sources(ghidra_cpp, src_dir)
        if copied == 0:
            die(f"copied 0 files from {ghidra_cpp} -- layout changed upstream?")
        status(f"copied {copied} files into vendored/src/")

    after = list_dir(src_dir)

    flake = vendored / "flake.nix"
    if flake.exists():
        status(f"updating vendored/flake.nix version to {version.short}")
        update_flake_version(flake, version.short)

    status("staging full vendored/ tree for orphan commit")
    git(["add", "-A"], cwd=vendored)

    status("bumping Cargo.toml version")
    new_cargo = bump_cargo_version(repo_root / "Cargo.toml", version.short)
    status(f"  Cargo.toml version -> {new_cargo}")

    status(f"updating .gitmodules branch to {version.branch}")
    git(
        ["config", "-f", ".gitmodules", "submodule.vendored.branch", version.branch],
        cwd=repo_root,
    )

    report = ImportReport(version=version, before=before, after=after)
    cmake_path = vendored / "CMakeLists.txt"
    refs = stale_cmake_refs(cmake_path, vendored)
    rendered = report.render(refs)

    report_path = repo_root / ".update-ghidra-report.txt"
    report_path.write_text(rendered)
    print(rendered, file=__import__("sys").stderr)
    status(f"report written to {report_path.name}")
    return report, report_path
