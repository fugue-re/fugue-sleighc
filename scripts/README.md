# Release automation

Tooling to sync. the vendored Ghidra code with a given release (by default latest).

## Prerequisites

- `git`
- `python3` (>= 3.10)
- An authenticated Claude Code session--the agent runs through
  `claude-agent-sdk`.
- A clean working tree in both the outer repo and `vendored/`.


## Usage

Setup a virtual environment:
```sh
scripts/setup-venv.sh
```

Perform an update:
```sh
fugue-sleighc-update update        # latest release
fugue-sleighc-update update 12.0.4 # explicit version
```

Update sub-steps (for debugging or manual iteration):

```sh
fugue-sleighc-update import [VERSION] # files only
fugue-sleighc-update reconcile        # agent only (reads .update-ghidra-report.txt)
```

`VERSION` accepts `12.1`, `Ghidra_12.1_build`, or `ghidra-v12.1`, otherwise
defaults to the latest GitHub release.

### Manual review and commit

The automation deliberately stops here so a human reviews the diffs.

```sh
git -C vendored diff --cached CMakeLists.txt # sanity-check agent edits
git -C vendored status

cd vendored
git commit -m "support for Ghidra v<VERSION>" # this is a root commit
git push -u origin ghidra-v<VERSION>
cd ..

git add vendored Cargo.toml .gitmodules
git commit -m "support for Ghidra v<VERSION>"
```
