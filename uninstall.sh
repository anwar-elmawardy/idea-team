#!/usr/bin/env bash
# Remove the idea team from ~/.claude. The agents' memory (~/.claude/agent-memory/) is kept.
set -euo pipefail
dest="${HOME}/.claude"
for a in senior-business-analyst senior-ui-ux-designer solution-architect application-architect \
         senior-technical-lead senior-qa-lead senior-backend-developer senior-frontend-developer \
         senior-qa-engineer senior-devops-engineer; do
  rm -f "$dest/agents/$a.md"
done
rm -rf "$dest/skills/idea-team"
rm -f "$dest/hooks/idea-team-guard.py"
echo "Removed. The agents' memory folders in $dest/agent-memory/ are still there; delete them by hand if you want."
