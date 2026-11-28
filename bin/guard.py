#!/usr/bin/env python3
"""PreToolUse hook: agents may edit and test inside their own worktree, never commit/push/merge, never touch .git,
never write outside FORGE_WRITE_ROOT, never run commands against a repo's main checkout (FORGE_PROTECT).
Exit 2 = block (message on stderr is shown to the agent)."""
import json, os, re, sys

BLOCKED = re.compile(
    r"\bgit\s+(commit|push|merge|rebase|reset|checkout|switch|cherry-pick|tag|stash|worktree|am|apply|pull|fetch|branch\s+(-[dDmM]|--delete|--move))\b"
    r"|\bgit\s+remote\s+(add|remove|rm|rename|set-url|prune)\b"
    r"|\bgh\s+(pr|release|repo)\b"
    r"|\bglab\s+mr\b"
    r"|\.git/"
    r"|\bcurl\b.*(-d|--data|-X\s*(POST|PUT|PATCH|DELETE))"
    r"|\brm\s+-rf\s+/"
)

def block(msg):
    print("BLOCKED by forge policy: " + msg, file=sys.stderr); sys.exit(2)

def under(path, root):
    try: return os.path.commonpath([os.path.realpath(path), root]) == root
    except ValueError: return False

def main():
    try: payload = json.load(sys.stdin)
    except Exception: sys.exit(0)
    tool = payload.get("tool_name", ""); inp = payload.get("tool_input", {}) or {}
    root = os.environ.get("FORGE_WRITE_ROOT"); root = os.path.realpath(root) if root else None
    protect = [os.path.realpath(p) for p in os.environ.get("FORGE_PROTECT", "").split(os.pathsep) if p]
    if tool == "Bash":
        cmd = inp.get("command", "")
        if BLOCKED.search(cmd): block("git write operations, PR creation and outbound POSTs are not permitted. Edit files and run tests only; the human commits.")
        for pr in protect:
            if pr in cmd and not (root and under(root, pr)):
                block(f"{pr} is a main checkout, not your worktree. The same files are in your worktree {root or os.getcwd()} under the same relative paths; use them. If the file you need is in a different repo, stop and write NO_CHANGES: wrong-repo: <name> as the first line of FORGE_SUMMARY.md.")
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = inp.get("file_path", "") or inp.get("notebook_path", "")
        if "/.git/" in path or path.endswith("/.git") or "/.forge/" in path: block("cannot write inside .git or .forge.")
        if root and path and not under(path, root):
            block(f"writes are confined to your worktree {root}; {path} is outside it. If the change belongs in another repo, stop and write NO_CHANGES: wrong-repo: <name> as the first line of FORGE_SUMMARY.md.")
    sys.exit(0)

if __name__ == "__main__":
    main()
