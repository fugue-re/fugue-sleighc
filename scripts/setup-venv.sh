#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [[ ! -d "$VENV" ]]; then
  echo "creating venv at $VENV" >&2
  python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install -e "$SCRIPT_DIR"

echo
echo "venv ready. Run with:"
echo "  $VENV/bin/fugue-sleighc-update update            # end-to-end"
echo "  $VENV/bin/fugue-sleighc-update import [VERSION]  # just the file import"
echo "  $VENV/bin/fugue-sleighc-update reconcile         # just the agent"
