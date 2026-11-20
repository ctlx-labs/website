#!/usr/bin/env python3
"""Claude Code PreToolUse hook: records are never edited (ctlx-labs/firm FIRM.md A12b, A13).

Blocks Edit, MultiEdit and Write on:
- an accepted decision: decisions/NNNN-*.md (or docs/decisions/) whose file says "Status: accepted".
  Allowed: creating a new decision; changing only the status line (to mark it superseded).
- any file under a folder named issued/ or records/ that already exists.
Exit code 2 blocks the action and shows the reason to the agent. Stamped from ctlxholdings/claude settings/firm/hooks/.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DECISION = re.compile(r"(^|/)decisions/\d{4}-[^/]+\.md$")
STATUS_LINE = re.compile(r"^\s*-?\s*Status:", re.IGNORECASE)


def only_status_change(tool_input: dict) -> bool:
    edits = tool_input.get("edits") or [tool_input]
    for e in edits:
        old, new = e.get("old_string", ""), e.get("new_string", "")
        if not old or "\n" in old.strip() or "\n" in new.strip():
            return False
        if not (STATUS_LINE.match(old) and STATUS_LINE.match(new)):
            return False
    return True


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if tool not in {"Edit", "MultiEdit", "Write"} or not path:
        return 0
    p = Path(path)
    if not p.exists():
        return 0  # creating a new file is always allowed
    posix = p.as_posix()

    if DECISION.search(posix):
        text = p.read_text(errors="ignore")
        if re.search(r"Status:\s*accepted", text, re.IGNORECASE):
            if tool != "Write" and only_status_change(ti):
                return 0
            print(f"Blocked: {path} is an accepted decision, a record that is never edited. "
                  "Write a new decision that supersedes it, then change only this file's status line.",
                  file=sys.stderr)
            return 2

    parts = set(p.parts)
    if parts & {"issued", "records"}:
        print(f"Blocked: {path} is an issued deliverable or record (A12b). Save a new version instead.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
