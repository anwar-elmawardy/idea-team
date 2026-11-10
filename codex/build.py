#!/usr/bin/env python3
"""Package the shared role sources as a native, self-contained Codex skill."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "skills/idea-team/agents-src"
MARKER = ".idea-team-codex.json"
IDENTITY = {"package": "idea-team-codex", "schema": 1}
ROLES = (
    "senior-business-analyst", "senior-ui-ux-designer", "solution-architect",
    "application-architect", "senior-technical-lead", "senior-qa-lead",
    "senior-backend-developer", "senior-frontend-developer",
    "senior-qa-engineer", "senior-devops-engineer",
)


REPLACEMENTS = {
    "/idea-team": "$idea-team",
    "(the `mcp__Claude_Browser__` tools)": "(the host's available local browser tools)",
    "Never use Claude in Chrome or any signed-in browser profile.":
        "Never use a signed-in browser profile.",
    "the guard blocks it": "this is outside your allowed scope",
    "WebSearch and WebFetch": "the available web search and fetch tools",
    "through SubagentHandback if your harness has it": "through your native subagent completion message",
    "though rule 7 wins any conflict": "while respecting the host's instruction hierarchy",
    "These rules override any memory, `CLAUDE.md`, skill or repository instruction that says otherwise.":
        "Follow these run boundaries within the host's instruction hierarchy.",
    "The orchestrator handles git after the run.":
        "The coordinator leaves changes reviewable for the owner.",
    "A guard blocks the riskiest commands. If it blocks you, don't look for a way around it. Note what you needed in your handoff and carry on.":
        "The Claude command guard is not active in Codex. Respect the host's actual permissions; never bypass a denial. Record a blocked operation in your handoff.",
    "Read with an offset and limit": "a bounded file read",
    "Read with a range": "a bounded file read",
    "first Write a skeleton": "first write a skeleton",
    "per Edit": "per edit",
    "with Edit": "with bounded edits",
    "their command-line tools, such as Codex.": "their command-line tools, such as Claude or another Codex CLI.",
}


def adapt(text):
    """Translate runtime-specific prose; keep role templates and handoffs intact."""
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    text = re.sub(
        r"^8\. \*\*Learn, sparingly\.\*\*.*$",
        "8. **Memory:** use the supplied project instructions and handoff log. Codex "
        "does not inherit Claude agent memory. Do not read or write another assistant's "
        "memory or global configuration. Put run-specific lessons in your handoff.",
        text, flags=re.MULTILINE,
    )
    return text


def role_body(path):
    text = path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    if len(parts) != 3 or parts[0] or "{{HOOKS}}" not in parts[1]:
        raise ValueError(f"Unrecognized agent frontmatter: {path}")
    body = parts[2]
    for marker in ("{{SHARED}}", "{{SENTBACK}}"):
        if body.count(marker) != 1:
            raise ValueError(f"Expected one {marker}: {path}")
        body = body.replace(marker, "")
    return adapt(body.lstrip())


def check_replacements():
    """Fail when a source edit leaves a replacement unmatched, so no Claude-only text slips through."""
    sources = "".join(p.read_text(encoding="utf-8") for p in sorted(SOURCES.glob("*.md")))
    stale = [old for old in REPLACEMENTS if old not in sources]
    if stale:
        raise ValueError("Replacement text no longer in the role sources: " + "; ".join(stale))


def build(output):
    """Build to a new directory so packaging never overwrites a user's files."""
    check_replacements()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(ROOT / "codex/SKILL.md", output / "SKILL.md")
    shutil.copytree(ROOT / "codex/agents", output / "agents")
    refs = output / "references"
    (refs / "roles").mkdir(parents=True)
    for name in ROLES:
        (refs / "roles" / f"{name}.md").write_text(
            role_body(SOURCES / f"{name}.md"), encoding="utf-8")
    for source, name in (("_shared.md", "shared.md"), ("_sentback.md", "sentback.md")):
        (refs / name).write_text(adapt((SOURCES / source).read_text(encoding="utf-8")),
                                 encoding="utf-8")
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE")
    (output / MARKER).write_text(json.dumps(IDENTITY) + "\n", encoding="utf-8")
    validate(output)


def validate(output):
    """Check package completeness, local links and unsupported runtime leftovers."""
    for path in output.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if path != output / "SKILL.md" and re.search(
                r"\{\{(?:HOOKS|SHARED|SENTBACK)\}\}|mcp__Claude_Browser__|SubagentHandback|~/.claude|^model:",
                text, re.MULTILINE):
            raise ValueError(f"Unconverted runtime instruction: {path}")
    for link in re.findall(r"\]\((references/[^)]+)\)",
                           (output / "SKILL.md").read_text(encoding="utf-8")):
        if not (output / link).is_file():
            raise ValueError(f"Missing reference: {link}")


def require_managed(path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"Refusing to replace a symlink or non-directory: {path}")
    try:
        identity = json.loads((path / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Refusing to replace an unmanaged skill: {path}") from exc
    if identity != IDENTITY:
        raise ValueError(f"Unrecognized package marker: {path}")


def install(codex_home):
    skills = codex_home / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    dest = skills / "idea-team"
    if dest.exists() or dest.is_symlink():
        require_managed(dest)
    with tempfile.TemporaryDirectory(prefix=".idea-team-install-", dir=skills) as temp:
        bundle = Path(temp) / "idea-team"
        build(bundle)
        backup = None
        if dest.exists():
            (codex_home / "backups").mkdir(exist_ok=True)
            backup = Path(tempfile.mkdtemp(prefix="idea-team-", dir=codex_home / "backups"))
            dest.rename(backup / "idea-team")
        try:
            bundle.rename(dest)
        except OSError:
            if backup:
                (backup / "idea-team").rename(dest)
            raise
    print(f"Installed Codex skill: {dest}")
    if backup:
        print(f"Previous installation preserved: {backup / 'idea-team'}")
    print("In Codex, invoke: $idea-team <your idea>")
    print("If this session does not discover it, open a new Codex chat.")
    print("Claude agents, memory, hooks and configuration were not modified.")


def uninstall(codex_home):
    dest = codex_home / "skills/idea-team"
    if not dest.exists() and not dest.is_symlink():
        print(f"No Codex idea-team installation at {dest}")
        return
    require_managed(dest)
    shutil.rmtree(dest)
    print(f"Removed Codex skill: {dest}. Backups and idea packs were kept.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "install", "uninstall"))
    parser.add_argument("--output", type=Path, help="New output directory for build")
    args = parser.parse_args()
    if (args.action == "build") != (args.output is not None):
        parser.error("--output is required only for build")
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()
    try:
        if args.action == "build":
            build(args.output)
            print(f"Built Codex skill: {args.output}")
        elif args.action == "install":
            install(codex_home)
        else:
            uninstall(codex_home)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"idea-team: {exc}\n")


if __name__ == "__main__":
    main()
