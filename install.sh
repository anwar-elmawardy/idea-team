#!/usr/bin/env bash
# Install or update the idea team into your Claude Code folder (~/.claude).
# Run from the repository folder: bash install.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dest="${HOME}/.claude"

command -v python3 >/dev/null || { echo "python3 is needed: install Python 3 first." >&2; exit 1; }

mkdir -p "$dest/skills" "$dest/hooks" "$dest/agents"
rm -rf "$dest/skills/idea-team"
cp -R "$here/skills/idea-team" "$dest/skills/idea-team"
cp "$here/hooks/idea-team-guard.py" "$dest/hooks/idea-team-guard.py"

python3 "$dest/skills/idea-team/agents-src/build.py"
python3 "$dest/hooks/idea-team-guard.py" --self-test

echo
echo "Installed. Start a new Claude Code session, then run: /idea-team <your idea>"
