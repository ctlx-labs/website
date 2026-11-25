#!/usr/bin/env python3
"""Claude Code PreToolUse hook: records and history are never rewritten (ctlx-labs/firm FIRM.md A12b, A13).

Edit, MultiEdit and Write are blocked on:
- an accepted decision: decisions/NNNN-*.md (or docs/decisions/) whose file says "Status: accepted".
  Allowed: creating a new decision; changing only the status line (to mark it superseded).
- any file under a folder named issued/ or records/ that already exists.
Bash is blocked when a command:
- changes one of those files: `sed -i`, `perl -i`, `>` or `>>` onto it, `tee`, `truncate`, `rm`, `mv`, `cp` onto it,
  `git rm`, `git mv` (creating a new file under records/ with `>` stays allowed);
- rewrites or deletes remote history: `git push` with `--force`, `-f`, `--force-with-lease`, `--force-if-includes`,
  `--mirror`, `--delete`, `-d`, a `+` refspec or a `:branch` refspec;
- deletes through the GitHub API: `gh api ... -X DELETE` or `--method DELETE`.
Exit code 2 blocks the action and shows the reason to the agent.
    python3 protect_records.py --self-test
Stamped from ctlxholdings/claude settings/firm/hooks/.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

DECISION = re.compile(r"(^|/)decisions/\d{4}-[^/]+\.md$")
STATUS_LINE = re.compile(r"^\s*-?\s*Status:", re.IGNORECASE)
FORCE_FLAGS = {"--force", "-f", "--force-with-lease", "--force-if-includes", "--mirror", "--delete", "-d"}


def only_status_change(tool_input: dict) -> bool:
    edits = tool_input.get("edits") or [tool_input]
    for e in edits:
        old, new = e.get("old_string", ""), e.get("new_string", "")
        if not old or "\n" in old.strip() or "\n" in new.strip():
            return False
        if not (STATUS_LINE.match(old) and STATUS_LINE.match(new)):
            return False
    return True


def protected(path: str, cwd: str) -> str | None:
    """Why an existing file may not change, or None."""
    p = Path(path) if os.path.isabs(path) else Path(cwd) / path
    if not p.exists():
        return None
    posix = p.as_posix()
    if DECISION.search(posix) and re.search(r"Status:\s*accepted", p.read_text(errors="ignore"), re.IGNORECASE):
        return (f"{path} is an accepted decision, a record that is never edited. Write a new decision that "
                "supersedes it, then change only this file's status line with the Edit tool.")
    if set(p.parts) & {"issued", "records"}:
        return f"{path} is an issued deliverable or record (A12b). Save a new version instead."
    return None


def segments(command: str) -> list[list[str]]:
    out = []
    for part in re.split(r"&&|\|\||;|\||\n", command):
        try:
            toks = shlex.split(part, posix=True)
        except ValueError:
            toks = part.split()
        if toks:
            out.append(toks)
    return out


def check_bash(command: str, cwd: str) -> str | None:
    for toks in segments(command):
        # Redirections onto an existing protected file (">" creating a new file is allowed).
        for m in re.finditer(r"(>>?)\s*([^\s;&|]+)", " ".join(shlex.quote(t) if " " in t else t for t in toks)):
            why = protected(m.group(2).strip("'\""), cwd)
            if why:
                return why
        cmd = toks[0]
        args = toks[1:]
        if cmd == "git" and args[:1] == ["push"]:
            rest = args[1:]
            bad = [a for a in rest if a in FORCE_FLAGS or a.startswith("--force")]
            refs = [a for a in rest if not a.startswith("-")][1:]  # after the remote
            bad += [r for r in refs if r.startswith("+") or r.startswith(":")]
            if bad:
                return (f"`git push {' '.join(rest)}` rewrites or deletes remote history ({bad[0]}). Branches are "
                        "never force-pushed or deleted by agents (AUTHORITY: Force-push; Delete a remote branch).")
        if cmd == "gh" and args[:1] == ["api"]:
            joined = " ".join(args)
            if re.search(r"(-X|--method)[ =]?DELETE\b", joined, re.IGNORECASE):
                return "`gh api` with DELETE removes something on GitHub; agents do not delete through the API."
        targets: list[str] = []
        if cmd in {"sed", "perl"} and any(a == "-i" or a.startswith("-i") or a.startswith("-pi") for a in args):
            targets = [a for a in args if not a.startswith("-")][1:]
        elif cmd in {"tee", "truncate", "rm", "shred"}:
            targets = [a for a in args if not a.startswith("-")]
        elif cmd in {"mv", "cp"}:
            plain = [a for a in args if not a.startswith("-")]
            targets = plain if cmd == "mv" else plain[-1:]
        elif cmd == "git" and args[:1] in (["rm"], ["mv"]):
            targets = [a for a in args[1:] if not a.startswith("-")]
        for t in targets:
            why = protected(t, cwd)
            if why:
                return why
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    cwd = event.get("cwd") or os.getcwd()
    if tool == "Bash":
        try:
            why = check_bash(str(ti.get("command", "")), cwd)
        except Exception as exc:  # fail safe
            print(f"protect_records.py skipped: {exc!r}", file=sys.stderr)
            return 0
        if why:
            print(f"Blocked: {why}", file=sys.stderr)
            return 2
        return 0
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if tool not in {"Edit", "MultiEdit", "Write"} or not path:
        return 0
    p = Path(path)
    if not p.exists():
        return 0  # creating a new file is always allowed
    if DECISION.search(p.as_posix()):
        text = p.read_text(errors="ignore")
        if re.search(r"Status:\s*accepted", text, re.IGNORECASE):
            if tool != "Write" and only_status_change(ti):
                return 0
            print(f"Blocked: {path} is an accepted decision, a record that is never edited. "
                  "Write a new decision that supersedes it, then change only this file's status line.",
                  file=sys.stderr)
            return 2
    if set(p.parts) & {"issued", "records"}:
        print(f"Blocked: {path} is an issued deliverable or record (A12b). Save a new version instead.",
              file=sys.stderr)
        return 2
    return 0


def self_test() -> int:
    import subprocess
    import tempfile

    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "records"))
    os.makedirs(os.path.join(d, "decisions"))
    open(os.path.join(d, "records", "r.md"), "w").write("x")
    open(os.path.join(d, "decisions", "0001-a.md"), "w").write("Status: accepted\n")
    open(os.path.join(d, "notes.md"), "w").write("x")

    def code(tool: str, ti: dict) -> int:
        out = subprocess.run([sys.executable, __file__], capture_output=True, text=True,
                             input=json.dumps({"tool_name": tool, "tool_input": ti, "cwd": d}))
        return out.returncode

    bash = lambda c: code("Bash", {"command": c})
    assert bash("sed -i 's/x/y/' records/r.md") == 2
    assert bash("echo y >> records/r.md") == 2
    assert bash("echo y > records/r.md") == 2
    assert bash("echo y > records/new.md") == 0  # a new record
    assert bash("rm decisions/0001-a.md") == 2
    assert bash("git mv records/r.md records/s.md") == 2
    assert bash("cp notes.md records/r.md") == 2
    assert bash("cp records/r.md notes2.md") == 0  # reading a record
    assert bash("sed -i 's/x/y/' notes.md") == 0
    assert bash("cat records/r.md | grep x") == 0
    assert bash("git push origin +main") == 2
    assert bash("git push origin :old-branch") == 2
    assert bash("git push --force-with-lease origin b") == 2
    assert bash("git push origin --delete b") == 2
    assert bash("git push -u origin claude/x") == 0
    assert bash("git push origin HEAD:refs/heads/claude/x") == 0
    assert bash("gh api -X DELETE repos/o/r/git/refs/heads/b") == 2
    assert bash("gh api repos/o/r/git/refs/heads/b --method DELETE") == 2
    assert bash("gh api repos/o/r/pulls") == 0
    assert code("Edit", {"file_path": os.path.join(d, "records", "r.md")}) == 2
    assert code("Write", {"file_path": os.path.join(d, "notes.md")}) == 0
    print("Self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv else main())
