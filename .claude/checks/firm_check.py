#!/usr/bin/env python3
"""Firm check, run in CI on every pull request and locally before a merge.

Fails when:
1. catalog-info.yaml is missing, or spec.owner is not a team (group:<team>)  (decision 0005).
2. An accepted decision changed in this branch other than its status line     (A13: decisions are records).
3. A connector (.mcp.json) or plugin (enabledPlugins) is not allowed for the team: allowed = adopt or trial
   in the team's manifest, stamped into .claude/kit-allowed.json             (radar rule).
5. Outside ctlx-labs/firm, the branch adds a firm rule file: a numbered decision (decisions/NNNN-*.md), FIRM.md,
   AUTHORITY.md, FILE-PLAN.md or RADAR.md. Firm rules live in one place (Ali, 15 Nov: "need to enforce the fact that
   we put all those in one place only"). Project decisions go in the project's specs/README.md.
6. governance/ROLES.md names, in its Script column, a file that does not exist (Ali, 15 Nov: "ok. implement all":
   a duty row may not run ahead of the work).
7. The pull request body hands Ali a task the agent could do itself ("one email would settle it", "you could ask
   them") on a line that does not list what was tried ("Tried:"). Text inside double quotes is a quotation and is
   skipped. Decision 0030 (Ali, 19 Nov: "until you extinguish all the options before you ask me"); correction #128.
Warns (does not fail) when:
4. The branch adds a file that looks like a new copy of a core asset, outside the asset's home and with no recorded
   exception (.claude/core-assets.json; ctlx-labs/firm catalog/CORE-ASSETS.md; FIRM.md B17).

    python3 .claude/checks/firm_check.py [--base origin/main]
Stamped from ctlxholdings/claude settings/firm/checks/.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()


def check_owner() -> list[str]:
    f = ROOT / "catalog-info.yaml"
    if not f.exists():
        return ["catalog-info.yaml missing: every repository needs a catalogue record with an owner team."]
    m = re.search(r"^\s*owner:\s*(\S+)", f.read_text(), re.MULTILINE)
    if not m:
        return ["catalog-info.yaml has no spec.owner."]
    owner = m.group(1).strip("'\"")
    if not owner.startswith("group:"):
        return [f"catalog-info.yaml owner is '{owner}': the owner must be a team, written group:<team>."]
    return []


def _moved_to_firm(name: str) -> bool:
    readme = ROOT / Path(name).parent / "README.md"
    return repo_name() != "firm" and readme.exists() and "ctlx-labs/firm" in readme.read_text()


def check_decisions(base: str) -> list[str]:
    try:
        changed = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=ROOT,
                                 capture_output=True, text=True, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []  # no base to compare with (first commit, shallow clone): skip
    out = []
    for name in changed:
        if not re.search(r"(^|/)decisions/\d{4}-[^/]+\.md$", name):
            continue
        old = subprocess.run(["git", "show", f"{base}:{name}"], cwd=ROOT, capture_output=True, text=True)
        if old.returncode != 0 or not re.search(r"Status:\s*accepted", old.stdout, re.IGNORECASE):
            continue  # new, or was not accepted
        new_path = ROOT / name
        if not new_path.exists() and _moved_to_firm(name):
            continue  # a copy removed because the record lives in ctlx-labs/firm (rule 5)
        new = new_path.read_text() if new_path.exists() else ""
        strip = lambda t: [l for l in t.splitlines() if not re.match(r"^\s*-?\s*Status:", l, re.IGNORECASE)]
        if strip(old.stdout) != strip(new):
            out.append(f"{name}: accepted decision changed. Write a new decision that supersedes it.")
    return out


def check_kit() -> list[str]:
    allowed_f = ROOT / ".claude" / "kit-allowed.json"
    if not allowed_f.exists():
        return []
    allowed = json.loads(allowed_f.read_text())
    ok_conn = {c.lower() for c in allowed.get("connectors", [])}
    ok_plug = {p.lower() for p in allowed.get("plugins", [])}
    out = []
    mcp = ROOT / ".mcp.json"
    if mcp.exists():
        for name in json.loads(mcp.read_text()).get("mcpServers", {}):
            if name.lower() not in ok_conn:
                out.append(f".mcp.json: connector '{name}' is not adopt or trial for this team (ctlx-labs/firm catalog/RADAR.md).")
    st = ROOT / ".claude" / "settings.json"
    if st.exists():
        for key, on in json.loads(st.read_text()).get("enabledPlugins", {}).items():
            if on and key.split("@")[0].lower() not in ok_plug:
                out.append(f".claude/settings.json: plugin '{key}' is not adopt or trial for this team.")
    return out


def repo_name() -> str:
    f = ROOT / "catalog-info.yaml"
    m = re.search(r"^\s*name:\s*(\S+)", f.read_text(), re.MULTILINE) if f.exists() else None
    return m.group(1).strip("'\"") if m else ROOT.name


def check_core_assets(base: str) -> list[str]:
    reg_f = ROOT / ".claude" / "core-assets.json"
    if not reg_f.exists():
        return []
    reg = json.loads(reg_f.read_text())
    try:
        added = subprocess.run(["git", "diff", "--name-only", "--diff-filter=A", f"{base}...HEAD"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    repo = repo_name()
    excepted = {e["asset"] for e in reg.get("exceptions", []) if e.get("repo") == repo}
    out = []
    for a in reg.get("assets", []):
        if repo in a.get("home", []) or a["id"] in excepted:
            continue
        hits = [n for n in added if any(fnmatch.fnmatch(n.lower(), p) or fnmatch.fnmatch(Path(n).name.lower(), p)
                                        for p in a["patterns"])]
        if hits:
            out.append(f"possible new copy of core asset {a['id']} ({a['name']}): {', '.join(hits[:5])}. "
                       "Use the shared asset, or record an exception or fork in ctlx-labs/firm catalog/CORE-ASSETS.md.")
    return out


FIRM_RULE_FILES = re.compile(r"(^|/)(decisions/\d{4}-[^/]+\.md|FIRM\.md|AUTHORITY\.md|FILE-PLAN\.md|RADAR\.md)$")


def check_one_place(base: str) -> list[str]:
    if repo_name() == "firm":
        return []
    try:
        added = subprocess.run(["git", "diff", "--name-only", "--diff-filter=A", f"{base}...HEAD"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [f"{n}: firm rules and decisions live only in ctlx-labs/firm. Write it there; project decisions go in "
            "specs/README.md." for n in added if FIRM_RULE_FILES.search(n)]


def check_roles() -> list[str]:
    f = ROOT / "governance" / "ROLES.md"
    if not f.exists():
        return []
    lines = f.read_text().splitlines()
    head = next((l for l in lines if l.startswith("| # |")), "")
    cols = [c.strip() for c in head.strip().strip("|").split("|")]
    if "Script" not in cols:
        return ["governance/ROLES.md has no Script column."]
    i = cols.index("Script")
    out = []
    for l in lines:
        if not re.match(r"^\|\s*\d+\s*\|", l):
            continue
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        script = cells[i] if i < len(cells) else ""
        if script and script != "none yet" and not (ROOT / script.split()[0]).exists():
            out.append(f"governance/ROLES.md duty {cells[0]} names {script}, which does not exist.")
    return out


HANDOFF = re.compile(
    r"\b(one (e-?mail|call|message)( to \S+)? (would|will|could) (settle|answer|resolve|confirm)"
    r"|you (could|can|may|might|should) (want to )?(e-?mail|ask|call|contact|check|write to|phone)"
    r"|could you (please )?(e-?mail|ask|call|contact|check|write to|phone)"
    r"|please (e-?mail|ask|call|contact|phone)\b"
    r"|ask (them|the vendor|the supplier)\b"
    r"|ali (could|can|should|needs to|to) (e-?mail|ask|call|contact|check|write to|phone))",
    re.IGNORECASE)


def find_handoffs(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        bare = re.sub(r'"[^"]*"|\u201c[^\u201d]*\u201d|`[^`]*`', "", line)
        if HANDOFF.search(bare) and "tried:" not in line.lower():
            out.append(line.strip())
    return out


def check_handoff() -> list[str]:
    body = os.environ.get("PR_BODY", "")
    return [f"PR body hands Ali a task: '{l[:120]}'. Do it yourself first (decision 0030), or add on the same line "
            "'Tried: <what was tried and what it returned>'." for l in find_handoffs(body)]


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        bad = ["One email to eInforma would settle it.", "You could ask them for the filing.",
               "Ali to email the registry."]
        good = ['Ali said "one email to eInforma would settle it" was wrong.', "Emailed the registry; reply attached.",
                "You could email them. Tried: help pages, terms, sample report; none name the filing date."]
        assert all(find_handoffs(t) for t in bad), [t for t in bad if not find_handoffs(t)]
        assert not any(find_handoffs(t) for t in good), [t for t in good if find_handoffs(t)]
        print("Self-test passed.")
        return 0
    base = argv[argv.index("--base") + 1] if "--base" in argv else "origin/main"
    problems = check_owner() + check_decisions(base) + check_kit() + check_one_place(base) + check_roles() + check_handoff()
    for w in check_core_assets(base):
        print(f"::warning::{w}")
        print(f"Warning: {w}")
    if problems:
        print("Firm check FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("Firm check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
