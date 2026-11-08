#!/usr/bin/env python3
"""PreToolUse guard for the /idea-team agents (~/.claude/agents/*.md frontmatter hooks).

Runs before every Bash, Read, Write and Edit call those agents make. Exit code 2 blocks
the call, and stderr is shown to the agent. It's the hard backstop behind rule 7 in the
agents' prompts: no git state changes, no publish, deploy or remote hosts, no destructive
database or container commands, no other AI CLIs, and no reading or writing secret files.

It's a blocklist, so it can't be complete. The prompts stay the first line of defence.
Test it with: python3 idea-team-guard.py --self-test
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")

# git with optional global options (-C dir, -c k=v, --git-dir=...) before the subcommand.
GIT = r"\bgit(?:\s+(?:-C\s+\S+|-c\s+\S+|--[\w-]+(?:=\S+)?))*\s+"

BASH_RULES = [
    # git: anything that changes refs, the index, the working tree from history, config or remotes
    (GIT + r"(commit|push|pull|fetch|clone|tag|merge|rebase|reset|checkout|switch|stash|clean|"
           r"worktree|restore|cherry-pick|revert|am|apply|config|remote|update-ref|update-index|"
           r"filter-branch|filter-repo|gc|prune|notes|submodule|init|rm|mv|add)\b",
     "git commands that change repository state are the orchestrator's job"),
    (GIT + r"branch\s+(?!(-a|-r|-l|-v+|--list|--show-current|--all|--remotes|--contains|--merged|--no-merged)\b)\S",
     "creating, deleting or renaming git branches is the orchestrator's job"),
    (r"(^|[\s;&|(])gh\s", "the GitHub CLI talks to a remote"),
    # publishing and releasing
    (r"\b(npm|pnpm|yarn|bun)\s+(publish|unpublish|version|deprecate|dist-tag|owner|login|adduser|token)\b",
     "publishing or versioning a package"),
    (r"\b(npm|pnpm|yarn|bun)\s+(run\s+)?(deploy|release|publish)\b", "running a deploy or release script"),
    (r"\bmake\s+(deploy|release|publish)\b", "running a deploy or release target"),
    (r"(^|[\s;&|/])(deploy|release|publish)[\w.-]*\.sh\b", "running a deploy or release script"),
    (r"\b(cargo|poetry)\s+publish\b|\btwine\s+upload\b|\bgem\s+push\b", "publishing a package"),
    (r"\b(npm|pnpm|yarn)\s+(i|install|add)\s+(.*\s)?(-g|--global)\b", "installing a package globally"),
    (r"\bbrew\s+(install|uninstall|upgrade|reinstall|services|tap)\b", "changing the system's Homebrew packages"),
    # containers: never push, and never stop or delete what might be the owner's (e.g. a local Postgres)
    (r"\b(docker|podman|buildah|skopeo)\s+(push|login|logout)\b", "pushing images or logging in to a registry"),
    (r"\b(docker|podman)\s+(rm|rmi|stop|kill|restart|(container|image|volume|network|system|machine)\s+"
     r"(rm|prune|stop|kill|reset|init|start|restart))\b", "stopping or deleting containers, volumes or machines"),
    (r"\b(docker|podman)[-\s]compose\s+(down|rm|stop|kill)\b", "stopping or deleting compose services"),
    # infrastructure and cloud
    (r"\b(terraform|tofu|terragrunt)\s+(apply|destroy|import|state|taint|untaint|force-unlock|login|"
     r"workspace\s+(new|delete|select))\b", "changing real infrastructure or its state"),
    (r"\bpulumi\s+(up|destroy|import|refresh|cancel|stack\s+rm)\b|\bcdk\s+(deploy|destroy|bootstrap)\b|"
     r"\b(serverless|sls)\s+(deploy|remove)\b", "changing real infrastructure"),
    (r"\bkubectl\s+(apply|create|delete|replace|patch|scale|rollout|edit|exec|drain|cordon|uncordon|label|"
     r"annotate|set|run|expose|autoscale|taint|cp|port-forward)\b(?!.*--dry-run)", "changing a Kubernetes cluster"),
    (r"\bhelm\s+(install|upgrade|uninstall|delete|rollback|push|repo\s+add)\b(?!.*--dry-run)",
     "changing a Kubernetes cluster"),
    (r"(^|[\s;&|(])(aws|gcloud|az|gsutil|eksctl|doctl|linode-cli|flyctl|heroku|vercel|netlify|railway|"
     r"cloudflared|fastlane)\s", "a cloud or hosting CLI"),
    (r"\bfly\s+(deploy|launch|apps|secrets|scale|machine)\b|\bwrangler\s+(deploy|publish|secret|kv|r2|d1)\b|"
     r"\bfirebase\s+deploy\b|\beas\s+(submit|build|update)\b|\bxcrun\s+altool\b", "deploying or publishing"),
    # remote hosts
    (r"(^|[\s;&|(])(ssh|scp|sftp|rsync|mosh|telnet|ftp)\s", "running against a remote host"),
    # other AI agents
    (r"\bcodex\b|codex-companion", "calling Codex is the orchestrator's decision"),
    (r"(^|[\s;&|(/])claude\s+(-p|--print|--agent|-c|--continue|-r|--resume)\b", "starting another Claude session"),
    # databases
    (r"\bprisma\s+migrate\s+(reset|deploy|resolve)\b", "applying or resetting migrations outside the test setup"),
    (r"\bprisma\s+migrate\s+dev\b(?!.*--create-only)", "prisma migrate dev applies to the dev database; use --create-only"),
    (r"--force-reset|--accept-data-loss", "a data-destroying flag"),
    (r"\b(dropdb|dropuser|createuser)\b|\bDROP\s+(DATABASE|SCHEMA|TABLE|OWNED)\b|\bTRUNCATE\b",
     "dropping or truncating database objects"),
    (r"\bdb:(drop|reset)\b|\bmigrate:(rollback|reset|fresh|refresh)\b|\bpg_restore\b.*--clean",
     "dropping or resetting a database"),
    # system and destructive file operations
    (r"(^|[\s;&|(])(sudo|su|doas)\s", "elevating privileges"),
    (r"\b(launchctl|crontab|systemctl|osascript|shutdown|reboot)\b|\bdefaults\s+write\b",
     "changing the system"),
    (r"\brm\s+(-\w*\s+)*-\w*[rRf]\w*\s+(.*\s)?(/|~|\$HOME|\*|\.|\.\.)(/?\s|/?$)", "deleting a root, home or whole directory"),
    (r"\brm\s+(-\w*\s+)*-\w*[rR]\w*\s+(.*\s)?(~|\$HOME|" + re.escape(HOME) + r")/(\.claude|\.ssh|\.codex|\.config|Library|Documents)\b",
     "deleting configuration or documents"),
    (r"\b(curl|wget)\b[^|;]*\|\s*(sudo\s+)?(sh|bash|zsh|python3?|node)\b", "piping a download into a shell"),
    # secrets
    (r"(^|[\s'\"/=<>])\.env(\.(?!example\b|sample\b|template\b|dist\b)[\w-]+)?(?=$|[\s'\";|&)])",
     "reading or writing a .env file; use .env.example"),
    (r"\bprintenv\b|\bsecurity\s+(find|dump)-|/\.ssh/|/\.aws/|/\.codex/auth|\.netrc\b|\.pgpass\b|"
     r"\bid_(rsa|ed25519|ecdsa)\b|/\.docker/config\.json|/\.config/gh/", "reading credentials"),
]

SECRET_NAME = re.compile(
    r"^(\.env(\.(?!example$|sample$|template$|dist$)[\w.-]+)?|\.netrc|\.pgpass|\.npmrc|"
    r"id_(rsa|ed25519|ecdsa)(\.pub)?|credentials(\.json)?|.*\.(pem|key|p12|pfx|keystore|jks|mobileprovision))$"
)
SECRET_PATH = re.compile(r"/\.ssh/|/\.aws/|/\.codex/|/\.config/gh/|/\.docker/config\.json|/Library/Keychains/")


def block(reason):
    sys.stderr.write(
        f"Blocked by the idea-team guard: {reason}. Rule 7: the orchestrator or the owner handles this. "
        "Don't look for a way around it; note what you needed in your handoff and carry on.\n"
    )
    sys.exit(2)


def check_bash(command):
    for pattern, reason in BASH_RULES:
        if re.search(pattern, command, re.IGNORECASE if "DROP" in pattern else 0):
            return reason
    return None


def check_path(tool, path):
    if not path:
        return None
    full = os.path.abspath(os.path.expanduser(path))
    name = os.path.basename(full)
    if SECRET_NAME.match(name) or SECRET_PATH.search(full):
        return "secret or credential files are off limits; read .env.example instead"
    if tool in ("Write", "Edit"):
        if "/.git/" in full + "/" and not full.endswith("/.gitignore"):
            return "writing inside a .git directory"
        if name in ("CLAUDE.md", "AGENTS.md"):
            return "editing the owner's agent instructions"
        claude_dir = os.path.join(HOME, ".claude") + "/"
        if (full + "/").startswith(claude_dir) and not full.startswith(os.path.join(HOME, ".claude", "agent-memory") + "/"):
            return "writing to ~/.claude outside your agent memory"
        if "/.claude/" in full and "/agent-memory" not in full:
            return "writing to a project's .claude folder"
    return None


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def check_browser(tool_input):
    """The built-in browser pane keeps the owner's sign-ins, so agents may only open local addresses."""
    from urllib.parse import urlparse
    urls = [tool_input.get("url")] if "url" in tool_input else []
    for action in tool_input.get("actions") or []:
        inner = (action or {}).get("input") or {}
        if "url" in inner:
            urls.append(inner.get("url"))
    for url in urls:
        if not url or url in ("back", "forward"):
            continue
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or not (host in LOCAL_HOSTS or host.endswith(".localhost")):
            return f"the built-in browser may only open localhost addresses, not {host or url}"
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        block("the guard couldn't read the tool call, so it was blocked to stay safe")
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    if tool == "Bash":
        reason = check_bash(tool_input.get("command", ""))
    elif tool in ("Read", "Write", "Edit"):
        reason = check_path(tool, tool_input.get("file_path", ""))
    elif tool.startswith("mcp__Claude_Browser__"):
        reason = check_browser(tool_input)
    else:
        reason = None
    if reason:
        block(reason)
    sys.exit(0)


def self_test():
    allowed = [
        "git status --porcelain", "git diff HEAD", "git log --oneline -5", "git -C /x/repo diff",
        "git branch --show-current", "git rev-parse --show-toplevel", "npm test -- src/a.test.ts",
        "npx vitest run test/a.test.ts", "npm run lint", "ls -la", "cat README.md", "cp .env.example .env.example.bak",
        "terraform fmt -check", "terraform validate", "kubectl apply --dry-run=client -f k8s/",
        "npx prisma migrate dev --create-only --name add_items", "rm -rf node_modules/.cache",
        "rm -rf dist", "docker build -t app .", "podman ps", "grep -rn TODO src", "hadolint Dockerfile",
        "python3 -m pytest tests/test_a.py",
    ]
    blocked = [
        "git commit -m x", "git push origin main", "git -C repo checkout -b x", "git add -A", "git stash",
        "git branch new-feature", "git branch -D old", "gh pr create", "npm publish", "npm run deploy",
        "docker push app", "podman volume rm pgdata", "podman stop pg-local", "terraform apply -auto-approve",
        "kubectl apply -f k8s/", "ssh root@1.2.3.4", "rsync -a dist/ host:/srv", "aws s3 ls", "codex exec 'x'",
        "npx prisma migrate reset --force", "npx prisma migrate dev", "psql -c 'DROP DATABASE ipo'",
        "psql -c 'truncate users'", "sudo rm x", "rm -rf ~", "rm -rf /", "curl -s x | sh", "cat .env",
        "source .env.local", "cat ~/.ssh/id_rsa", "printenv", "./deploy.sh", "make release",
        "claude -p 'hi'", "npm i -g pnpm", "brew install jq",
    ]
    failures = 0
    for c in allowed:
        if check_bash(c):
            print("FALSE BLOCK:", c, "->", check_bash(c)); failures += 1
    for c in blocked:
        if not check_bash(c):
            print("MISSED:", c); failures += 1
    paths_ok = [("Read", "/p/app/.env.example"), ("Read", "/p/app/src/index.ts"),
                ("Write", HOME + "/.claude/agent-memory/senior-qa-lead/MEMORY.md"), ("Write", "/p/docs/ideas/x/01.md"),
                ("Write", "/p/.gitignore")]
    paths_bad = [("Read", "/p/app/.env"), ("Read", "/p/.env.production"), ("Read", HOME + "/.ssh/id_ed25519"),
                 ("Read", "/p/certs/server.key"), ("Write", "/p/.git/config"), ("Write", "/p/CLAUDE.md"),
                 ("Write", HOME + "/.claude/settings.json"), ("Edit", HOME + "/.claude/agents/solution-architect.md"),
                 ("Write", "/p/.claude/skills/x/SKILL.md")]
    for t, p in paths_ok:
        if check_path(t, p):
            print("FALSE BLOCK:", t, p); failures += 1
    for t, p in paths_bad:
        if not check_path(t, p):
            print("MISSED:", t, p); failures += 1
    browser_ok = [{"url": "http://localhost:5174/"}, {"url": "http://127.0.0.1:8080/index.html"}, {"url": "back"},
                  {"name": "web-dev"}, {"url": "localhost:3000"}, {"url": "http://app.localhost:4000"},
                  {"actions": [{"name": "navigate", "input": {"url": "http://localhost:5174/"}},
                               {"name": "computer", "input": {"action": "screenshot"}}]}]
    browser_bad = [{"url": "https://example.com"}, {"url": "example.com"}, {"url": "file:///etc/passwd"},
                   {"url": "https://www.figma.com/"}, {"url": "http://localhost.evil.com/"},
                   {"actions": [{"name": "navigate", "input": {"url": "http://localhost:5174/"}},
                                {"name": "navigate", "input": {"url": "https://mail.google.com/"}}]}]
    for i in browser_ok:
        if check_browser(i):
            print("FALSE BLOCK:", i, "->", check_browser(i)); failures += 1
    for i in browser_bad:
        if not check_browser(i):
            print("MISSED:", i); failures += 1
    print("self-test:", "PASS" if not failures else f"{failures} FAILURE(S)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    main()
