#!/usr/bin/env python3
"""Rebuild ~/.claude/agents/*.md for the /idea-team agents from these sources.

Edit _shared.md (the team table and rules every agent shares), _sentback.md (revision and
handoff rules), or one agent's <name>.md, then run: python3 build.py
Each agent source holds its frontmatter and role text, with {{HOOKS}}, {{SHARED}} and
{{SENTBACK}} where the shared parts go. A new Claude Code session picks up the result.
"""
import glob
import os

here = os.path.dirname(os.path.abspath(__file__))
shared = open(os.path.join(here, "_shared.md")).read().rstrip("\n")
sentback = open(os.path.join(here, "_sentback.md")).read().rstrip("\n")
guard = os.path.expanduser("~/.claude/hooks/idea-team-guard.py")
hooks = ('hooks:\n  PreToolUse:\n    - matcher: "Bash|Read|Write|Edit|mcp__Claude_Browser__navigate|mcp__Claude_Browser__preview_start|mcp__Claude_Browser__browser_batch"\n      hooks:\n'
         f"        - type: command\n          command: \"python3 '{guard}'\"")
out = os.path.expanduser("~/.claude/agents")
os.makedirs(out, exist_ok=True)
for src in sorted(glob.glob(os.path.join(here, "[a-z]*.md"))):
    text = open(src).read()
    for marker, value in (("{{HOOKS}}", hooks), ("{{SHARED}}", shared), ("{{SENTBACK}}", sentback)):
        assert text.count(marker) == 1, f"{src}: expected one {marker}"
        text = text.replace(marker, value)
    open(os.path.join(out, os.path.basename(src)), "w").write(text)
    print("built", os.path.basename(src))
