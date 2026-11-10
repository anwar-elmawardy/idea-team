#!/usr/bin/env bash
# Install for Claude Code (default) or Codex (--codex).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
  --codex) exec python3 "$here/codex/build.py" install "${@:2}" ;;
  --claude) shift ;;
  "") ;;
  *) echo "Usage: bash install.sh [--claude | --codex]" >&2; exit 2 ;;
esac
if (( $# )); then
  echo "Usage: bash install.sh [--claude | --codex]" >&2
  exit 2
fi
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
