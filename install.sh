#!/usr/bin/env bash
# One-time setup on a new machine/account. Idempotent.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$HERE/bin/forge" "$HERE/bin/guard.py"

command -v claude >/dev/null || { echo "install Claude Code first: npm i -g @anthropic-ai/claude-code && claude login"; exit 1; }
command -v python3 >/dev/null || { echo "python3 required"; exit 1; }

if grep -q '/ABSOLUTE/PATH/TO/REPO' "$HERE/forge.json"; then
  read -rp "Absolute path to the repo forge should work on: " REPO
  python3 - "$HERE/forge.json" "$REPO" <<'PY'
import json,sys
p,repo=sys.argv[1],sys.argv[2]
c=json.load(open(p)); c["repo"]=repo; json.dump(c,open(p,"w"),indent=2)
PY
fi

"$HERE/bin/forge" init
echo
echo "Add to your shell profile:   export PATH=\"$HERE/bin:\$PATH\""
echo "Then:  forge plan tickets/example.md && forge loop"
