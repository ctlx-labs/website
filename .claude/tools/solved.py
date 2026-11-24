#!/usr/bin/env python3
"""solved.py: has this been solved already? Search every ctlx-labs repository before building.

    python3 .claude/tools/solved.py "weekly monthly period" "period stated year" [--repo NAME] [--local DIR] [--top N]

Give two to four phrasings of the problem in plain words (what it does, not what you would call the function).
Each phrasing is one GitHub code search over the whole organisation (all repositories, private included, default
branch). Files found by more phrasings rank first. For the top files it prints the lines that hold the words, as
repo/path:line. --local DIR also runs ripgrep over a local folder (clones, unmerged branches, work not on GitHub).

Uses the GitHub index, so there is nothing to build or refresh. Needs `gh` signed in (the Mac, and cloud sessions,
have it). Limits: default branch only; code search allows about 10 searches a minute; words must appear in the file
(no synonyms), so phrase it more than one way. Standard library only.
[added 20 Nov 2026, workshop; thread "3-WKS-FIRM Searchable index of what we've built"]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time

ORG = "ctlx-labs"
# Left out unless --all: scratch runs, superseded copies, and answer keys (oracles are not for the building agent).
SKIP = re.compile(r"(^|/)(\.probe|archive|archived|oracles?|held[-_]back|node_modules|vendor)(/|$)", re.I)
CODE = re.compile(r"\.(py|js|ts|sh|r|jl|sql|ipynb)$", re.I)
RULES = re.compile(r"(spec|law|decision|polic|rule|register|finding|ledger|microcase|catalog|FIRM\.md|CLAUDE\.md|"
                   r"AGENT-RULES|DESIGN|INVENTORY|COMPONENTS)", re.I)


def kind(path: str) -> str:
    return "code" if CODE.search(path) else "rules, specs, registers" if RULES.search(path) else "notes and other"


def gh(args: list[str]) -> str:
    r = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.stdout


def search(phrase: str, per_page: int, repos: list[str]) -> list[dict]:
    scope = " ".join(f"repo:{ORG}/{r}" for r in repos) if repos else f"org:{ORG}"
    for attempt in range(3):
        try:
            out = gh(["-X", "GET", "search/code", "-f", f"q={phrase} {scope}", "-f", f"per_page={per_page}",
                      "-H", "Accept: application/vnd.github.text-match+json"])
            return json.loads(out).get("items", [])
        except RuntimeError as e:
            if "rate limit" in str(e).lower() and attempt < 2:
                time.sleep(30)
                continue
            raise
    return []


def words(phrase: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[\w\-]+", phrase) if len(w) > 1]


def best_lines(text: str, terms: set[str], n: int = 3) -> list[tuple[int, str]]:
    scored = []
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        s = sum(1 for t in terms if t in low)
        if s:
            scored.append((s, i, line.strip()))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return sorted((i, l[:160]) for _, i, l in scored[:n])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phrases", nargs="+", help="plain-word phrasings of the problem")
    ap.add_argument("--top", type=int, default=12, help="files to show (default 12)")
    ap.add_argument("--local", help="also search this local folder with ripgrep")
    ap.add_argument("--repo", action="append", default=[], help="limit to this repository (repeatable)")
    ap.add_argument("--all", action="store_true", help="include .probe, archive and oracle folders")
    a = ap.parse_args()

    hits: dict[str, dict] = {}
    for k, phrase in enumerate(a.phrases):
        if k:
            time.sleep(6)  # code search: about 10 a minute
        try:
            items = search(phrase, 50, a.repo)
        except RuntimeError as e:
            print(f"search failed for '{phrase}': {e}", file=sys.stderr)
            continue
        for rank, it in enumerate(items):
            if not a.all and SKIP.search(it["path"]):
                continue
            key = f"{it['repository']['name']}/{it['path']}"
            h = hits.setdefault(key, {"repo": it["repository"]["name"], "path": it["path"], "phrases": set(),
                                      "rank": rank, "frags": []})
            h["phrases"].add(phrase)
            h["rank"] = min(h["rank"], rank)
            h["frags"] += [m.get("fragment", "") for m in it.get("text_matches", [])]
        print(f"'{phrase}': {len(items)} files", file=sys.stderr)

    ranked = sorted(hits.values(), key=lambda h: (-len(h["phrases"]), h["rank"]))[: a.top]
    print(f"\n# GitHub ({ORG}, default branches): {len(hits)} files, top {len(ranked)}")
    for group in ("code", "rules, specs, registers", "notes and other"):
        rows = [h for h in ranked if kind(h["path"]) == group]
        if not rows:
            continue
        print(f"\n## {group}\n")
        for h in rows:
            terms = {w for p in h["phrases"] for w in words(p)}
            print(f"{h['repo']}/{h['path']}   [{len(h['phrases'])} of {len(a.phrases)} phrasings]")
            try:
                raw = gh([f"repos/{ORG}/{h['repo']}/contents/{h['path']}", "-H", "Accept: application/vnd.github.raw"])
                for i, line in best_lines(raw, terms):
                    print(f"    :{i}  {line}")
            except RuntimeError:
                # No read access to the file (e.g. a cloud session): show the matched text instead of line numbers.
                for i, line in best_lines("\n".join(h["frags"]), terms):
                    print(f"    ~  {line}")

    if a.local:
        if not shutil.which("rg"):
            print("\nripgrep (rg) not installed; skipped --local", file=sys.stderr)
        else:
            print(f"\n# Local: {a.local}\n")
            for phrase in a.phrases:
                ws = words(phrase)
                if not ws:
                    continue
                # files holding every word of the phrase, then their lines with the rarest word
                files = subprocess.run(["rg", "-l", "-i", "-F", ws[0], a.local], capture_output=True,
                                       text=True).stdout.split()
                for w in ws[1:]:
                    files = [f for f in files if subprocess.run(["rg", "-q", "-i", "-F", w, f]).returncode == 0]
                print(f"'{phrase}': {len(files)} files")
                for f in files[: a.top]:
                    print(f"    {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
