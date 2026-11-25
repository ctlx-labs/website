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
8. Outside ctlx-labs/one-engine, the branch adds a financial calculation function (irr, npv, xirr, xnpv, dscr, llcr,
   pmt, annuity, waterfall, payback) in Python, JavaScript or TypeScript. Figures used for decisions or sent out come
   from golden-tested one-engine code (decision 0035): call one-engine instead. Test files and the allow-listed
   teaching code (FINANCE_ALLOWED) are skipped. Existing definitions are not flagged; only added lines are read.
9. catalog-info.yaml gives `ctlx-labs/kind` or `ctlx-labs/unit` (metadata.annotations) a value outside the lists:
   kind machine | work | records (decision 0029, FIRM.md B17 iteration 4); unit line:<name> | core-assets | workshop |
   management-system | office (decision 0025). A `records` repository whose branch edits or deletes an existing
   file also fails (A12b: a record is never edited; a change is a new dated file).
11. The repository has specs/README.md without an "Oracle: outside <reference>" or "Oracle: graded <file>" line
    ("Oracle: built" alone fails). Same wording as gate 1.6e in ctlx-labs/myralphloop check_process.py, enforced by
    loop.sh since 19 Nov; this extends it to builds outside myralphloop (review 24 Nov, ctlx-labs/firm PR #188).
12. Two decision files share a number (decisions/NNNN-*.md), or the branch adds a decision whose number the base
    (origin/main) already holds under another name. Parallel branches claimed 0044 and 0045 twice on 24 Nov 2026
    (ctlx-labs/firm #217); take the next free number after merging main.
13. Two rows of ops/purchases.csv share an id, or the branch adds an id (absent at the merge base) that the base
    (origin/main) already holds. Parallel branches claimed P19 and P32 twice on 24 Nov 2026; same shape as rule 12.
14. A YAML (.yaml, .yml) or JSON (.json) file that the branch adds or changes does not parse. Invalid YAML merged
    in thesis-esco on 25 Nov (tiers.yaml v0.4, design/investor_profiles.yaml) because no check read it. Unknown YAML
    tags are accepted. Skipped: JSON-with-comments files (tsconfig*.json, jsconfig*.json, .vscode/, .devcontainer/) and
    vendored or fixture folders (node_modules, vendor, external, test(s), fixture(s)). Unchanged files that do not
    parse are warnings.
Warns (does not fail) when:
4. The branch adds a file that looks like a new copy of a core asset, outside the asset's home and with no recorded
   exception (.claude/core-assets.json; ctlx-labs/firm catalog/CORE-ASSETS.md; FIRM.md B17).
10. catalog-info.yaml has no `ctlx-labs/kind` or no `ctlx-labs/unit` (rollout: a warning until every repository
    carries both, register in ctlx-labs/firm catalog/KINDS.md; then it moves to rule 9). A `work` repository whose
    branch adds code (.py, .js, .ts, .R, .jl, .ipynb) outside .claude/ and .github/: a work repository holds inputs
    and configuration that a machine reads, not calculations of its own (B17 iteration 4, rule 2).

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


DECISION_FILE = re.compile(r"(^|/)decisions/(\d{4})-[^/]+\.md$")


def decision_number_problems(tree: list[str], added: list[str], base_tree: list[str]) -> list[str]:
    """Rule 12: no two decisions share a number; a decision added here does not reuse a number the base holds."""
    def numbers(names):
        by = {}
        for n in names:
            m = DECISION_FILE.search(n)
            if m:
                by.setdefault((n[:m.start(2)], m.group(2)), []).append(n)
        return by
    out = []
    for (_, num), names in sorted(numbers(tree).items()):
        if len(names) > 1:
            out.append(f"decision number {num} is used by {len(names)} files: {', '.join(sorted(names))}. "
                       "Renumber the newer one to the next free number.")
    on_base = numbers(base_tree)
    for n in added:
        m = DECISION_FILE.search(n)
        if not m:
            continue
        taken = [b for b in on_base.get((n[:m.start(2)], m.group(2)), []) if b != n]
        if taken:
            out.append(f"{n}: number {m.group(2)} is already taken on the base by {taken[0]}. "
                       "Merge the base and take the next free number.")
    return out


def check_decision_numbers(base: str) -> list[str]:
    def git(*args):
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        return r.stdout.split("\n") if r.returncode == 0 else []
    tree = [n for n in git("ls-files") if n]
    added = [n for n in git("diff", "--name-only", "--diff-filter=A", f"{base}...HEAD") if n]
    base_tree = [n for n in git("ls-tree", "-r", "--name-only", base) if n]
    return decision_number_problems(tree, added, base_tree)


PURCHASES = "ops/purchases.csv"


def purchase_ids(text: str) -> list[str]:
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(text or "")))
    return [(r.get("id") or "").strip() for r in rows if (r.get("id") or "").strip()]


def purchase_id_problems(head: str, fork: str, base: str) -> list[str]:
    """Rule 13: ids in ops/purchases.csv are unique, and a branch does not add an id the base already holds."""
    ids = purchase_ids(head)
    out = [f"{PURCHASES}: id {i} is used by {ids.count(i)} rows. Give the newer row the next free id."
           for i in sorted({i for i in ids if ids.count(i) > 1})]
    added = set(ids) - set(purchase_ids(fork))
    for i in sorted(added & set(purchase_ids(base))):
        out.append(f"{PURCHASES}: id {i} is added on this branch but the base already holds it. "
                   "Merge the base and take the next free id.")
    return out


def check_purchase_ids(base: str) -> list[str]:
    if not (ROOT / PURCHASES).exists():
        return []
    def show(ref):
        r = subprocess.run(["git", "show", f"{ref}:{PURCHASES}"], cwd=ROOT, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""
    mb = subprocess.run(["git", "merge-base", base, "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return purchase_id_problems((ROOT / PURCHASES).read_text(), show(mb) if mb else "", show(base))


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


FINANCE_DEF = re.compile(
    r"^\+\s*(?:export\s+)?(?:async\s+)?(?:def|function|const|let|var)\s+_*(?:calc(?:ulate)?_?)?"
    r"(irr|npv|xirr|xnpv|dscr|llcr|pmt|annuity|waterfall|payback)\b", re.IGNORECASE)
FINANCE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".mjs")
# Teaching code and the workshop's own golden case (decision 0035; register rows 14, 15, 17-19).
FINANCE_ALLOWED = {
    "one-engine": ["*"],
    "stochastic-course-app": ["*"],
    "risk-return-simulator": ["*"],
    "chad-2030-simulator": ["*"],
    "myralphloop": ["projects/returns-model/*", "examples/loan-demo/*"],
}


def is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return (any(p in ("test", "tests", "__tests__", "spec") for p in parts[:-1]) or name.startswith("test_")
            or re.search(r"(_test\.py|\.(test|spec)\.[jt]sx?)$", name) is not None)


def finance_defs(diff: str, repo: str) -> list[str]:
    allowed = FINANCE_ALLOWED.get(repo, [])
    out, path = [], ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
            continue
        if not path or not path.endswith(FINANCE_EXT) or is_test_path(path):
            continue
        if any(fnmatch.fnmatch(path, a) for a in allowed):
            continue
        m = FINANCE_DEF.match(line)
        if m:
            out.append(f"{path}: adds a {m.group(1).lower()} function. Financial calculation runs on one-engine "
                       "(decision 0035): call one_engine.measures or the pack that has it, or extend one-engine "
                       "through its own intake.")
    return out


def check_finance(base: str) -> list[str]:
    try:
        diff = subprocess.run(["git", "diff", "-U0", "--diff-filter=AM", f"{base}...HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return finance_defs(diff, repo_name())


KINDS = ("machine", "work", "records")
UNITS = re.compile(r"^(line:[a-z0-9][a-z0-9-]*|core-assets|workshop|management-system|office)$")
CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".r", ".jl", ".ipynb")


def catalog_fields(text: str) -> dict[str, str]:
    """ctlx-labs/* annotations of the first catalogue document (the Component)."""
    first = text.split("\n---")[0]
    return {k: v.strip().strip("'\"") for k, v in
            re.findall(r"^\s+ctlx-labs/(kind|unit):\s*(\S+)", first, re.MULTILINE)}


def kind_problems(fields: dict[str, str]) -> tuple[list[str], list[str]]:
    fails, warns = [], []
    kind, unit = fields.get("kind"), fields.get("unit")
    if kind is None:
        warns.append("catalog-info.yaml has no ctlx-labs/kind annotation (machine | work | records; decision 0029).")
    elif kind not in KINDS:
        fails.append(f"catalog-info.yaml ctlx-labs/kind is '{kind}': use machine, work or records (decision 0029).")
    if unit is None:
        warns.append("catalog-info.yaml has no ctlx-labs/unit annotation (line:<name> | core-assets | workshop | "
                     "management-system | office; decision 0025).")
    elif not UNITS.match(unit):
        fails.append(f"catalog-info.yaml ctlx-labs/unit is '{unit}': use line:<name>, core-assets, workshop, "
                     "management-system or office (decision 0025).")
    return fails, warns


def kind_diff_problems(kind: str | None, status_lines: list[str]) -> tuple[list[str], list[str]]:
    """status_lines: `git diff --name-status` rows (A/M/D/Rnn, tab, path)."""
    fails, warns = [], []
    for row in status_lines:
        parts = row.split("\t")
        if len(parts) < 2:
            continue
        st, path = parts[0][:1], parts[-1]
        if path.startswith((".claude/", ".github/")) or path in ("catalog-info.yaml", "CLAUDE.md"):
            continue  # stamped settings and the catalogue record itself
        if kind == "records" and st in ("M", "D", "R"):
            fails.append(f"{parts[1]}: edited or removed in a records repository. A record is never edited; add a "
                         "new dated version (A12b).")
        if kind == "work" and st == "A" and path.lower().endswith(CODE_EXT):
            warns.append(f"{path}: code added to a work repository. Calculations belong in a machine that reads this "
                         "repository's inputs (B17 iteration 4, rule 2).")
    return fails, warns


def check_kind(base: str) -> tuple[list[str], list[str]]:
    f = ROOT / "catalog-info.yaml"
    if not f.exists():
        return [], []  # rule 1 already fails it
    fields = catalog_fields(f.read_text())
    fails, warns = kind_problems(fields)
    try:
        rows = subprocess.run(["git", "diff", "--name-status", f"{base}...HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        rows = []
    f2, w2 = kind_diff_problems(fields.get("kind"), rows)
    return fails + f2, warns + w2


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


ORACLE = re.compile(r"(?mi)^Oracle:[ \t]*(outside|graded|built)\b[ \t]*(.*)$")


def oracle_problem(readme: str) -> str | None:
    m = ORACLE.search(readme)
    if m and m.group(1).lower() != "built" and m.group(2).strip():
        return None
    return ("specs/README.md needs 'Oracle: outside <reference>' or 'Oracle: graded <file of the person's grades>'; "
            "'Oracle: built' alone fails: build the check first, then the product (myralphloop gate 1.6e).")


def check_oracle() -> list[str]:
    readme = ROOT / "specs" / "README.md"
    if not readme.exists():
        return []
    p = oracle_problem(readme.read_text(errors="ignore"))
    return [p] if p else []


JSONC = ("tsconfig*.json", "jsconfig*.json", "*.jsonc")
# Vendored or deliberately broken files: third-party packages, outside oracle suites, test fixtures.
PARSE_SKIP_DIRS = {"node_modules", "vendor", "external", "test", "tests", "fixture", "fixtures", ".vscode",
                   ".devcontainer"}


def parse_problem(path: str, text: str) -> str | None:
    """Why the YAML or JSON text does not parse, or None when it does (or the file is neither)."""
    if (any(fnmatch.fnmatch(Path(path).name, g) for g in JSONC)
            or PARSE_SKIP_DIRS.intersection(Path(path).parts[:-1])):
        return None
    try:
        if path.endswith(".json"):
            json.loads(text)
        elif path.endswith((".yaml", ".yml")):
            import yaml

            class Loader(yaml.SafeLoader):
                pass
            Loader.add_multi_constructor("", lambda loader, suffix, node: None)
            list(yaml.load_all(text, Loader=Loader))
        return None
    except ImportError:
        return "PyYAML is not installed; the workflow installs it (pip install pyyaml)"
    except Exception as e:  # noqa: BLE001 - any parse error is the finding
        return " ".join(str(e).split())[:300]


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def check_parse(base: str) -> tuple[list[str], list[str]]:
    """Rule 14: changed YAML and JSON files parse (fail); other tracked ones that do not are warnings."""
    changed = set(_git("diff", "--name-only", "--diff-filter=AMR", f"{base}...HEAD").split())
    fails, warns = [], []
    for path in _git("ls-files", "*.yaml", "*.yml", "*.json").split("\n"):
        if not path or not (ROOT / path).is_file():
            continue
        why = parse_problem(path, (ROOT / path).read_text(errors="replace"))
        if why:
            (fails if path in changed else warns).append(f"{path} does not parse (rule 14): {why}")
    if len(warns) > 10:
        warns = warns[:10] + [f"{len(warns) - 10} more YAML or JSON files do not parse (rule 14)"]
    return fails, warns


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        bad = ["One email to eInforma would settle it.", "You could ask them for the filing.",
               "Ali to email the registry."]
        good = ['Ali said "one email to eInforma would settle it" was wrong.', "Emailed the registry; reply attached.",
                "You could email them. Tried: help pages, terms, sample report; none name the filing date."]
        assert all(find_handoffs(t) for t in bad), [t for t in bad if not find_handoffs(t)]
        assert not any(find_handoffs(t) for t in good), [t for t in good if find_handoffs(t)]
        diff = ("+++ b/engine/returns.py\n+def irr(flows):\n+def _npv(r, flows):\n+    x = irr(f)\n"
                "+++ b/src/model.js\n+export function calculateIRR(cf) {\n+const dscr = (a, b) => a / b;\n"
                "+++ b/engine/tests/test_returns.py\n+def irr(flows):\n"
                "+++ b/projects/returns-model/src/returns/irr.py\n+def irr(flows):\n"
                "+++ b/README.md\n+def irr(flows):\n")
        hits = finance_defs(diff, "myralphloop")
        assert len(hits) == 4, hits
        assert not finance_defs(diff, "one-engine")
        cat = ("apiVersion: backstage.io/v1alpha1\nkind: Component\nmetadata:\n  name: x\n  annotations:\n"
               "    ctlx-labs/kind: work\n    ctlx-labs/unit: line:investing\nspec:\n  type: data\n---\n"
               "kind: System\nmetadata:\n  annotations:\n    ctlx-labs/kind: bogus\n")
        assert catalog_fields(cat) == {"kind": "work", "unit": "line:investing"}, catalog_fields(cat)
        assert kind_problems(catalog_fields(cat)) == ([], [])
        assert len(kind_problems({})[1]) == 2 and not kind_problems({})[0]
        assert len(kind_problems({"kind": "tooling", "unit": "deals"})[0]) == 2
        assert not kind_problems({"kind": "records", "unit": "management-system"})[0]
        rows = ["M\tissued/memo.md", "A\tissued/memo-v2.md", "M\t.claude/checks/firm_check.py", "D\told.md",
                "A\tmodel/calc.py", "A\tinputs/case.yaml", "A\t.github/x.py"]
        assert len(kind_diff_problems("records", rows)[0]) == 2
        assert len(kind_diff_problems("work", rows)[1]) == 1 and not kind_diff_problems("work", rows)[0]
        assert kind_diff_problems("machine", rows) == ([], [])
        assert oracle_problem("Oracle: outside html5lib tests") is None
        assert oracle_problem("x\nOracle: graded tests/grades.csv\n") is None
        assert oracle_problem("Oracle: built") and oracle_problem("Oracle: outside") and oracle_problem("no line")
        t = ["decisions/0044-a.md", "decisions/0045-b.md", "decisions/0045-c.md", "decisions/README.md"]
        assert len(decision_number_problems(t, [], [])) == 1
        assert not decision_number_problems(t[:2], ["decisions/0045-b.md"], t[:1])
        assert len(decision_number_problems(["decisions/0045-b.md"], ["decisions/0045-b.md"],
                                            ["decisions/0045-x.md"])) == 1
        assert not decision_number_problems(["specs/decisions/0001-a.md", "decisions/0001-b.md"], [], [])
        h = "id,item\nP01,a\nP02,b\nP02,c\n"
        assert len(purchase_id_problems(h, "", "")) == 1
        assert not purchase_id_problems("id,item\nP01,a\nP02,b2\n", "id,item\nP01,a\nP02,b\n",
                                        "id,item\nP01,a\nP02,b\nP03,x\n")
        assert len(purchase_id_problems("id,item\nP01,a\nP03,y\n", "id,item\nP01,a\n",
                                        "id,item\nP01,a\nP03,x\n")) == 1
        assert parse_problem("a.yaml", "a: 1\n---\nb: !Ref x\n") is None
        assert parse_problem("a.yaml", "a: [1, 2\nb: 3\n")
        assert parse_problem("a.json", '{"a": 1,}') and parse_problem("x.json", '{"a": 1}') is None
        assert parse_problem("p/tests/inputs/bad.json", "x") is None and parse_problem("x/node_modules/a.json", "x") is None
        assert parse_problem("tsconfig.json", "{// c\n}") is None and parse_problem("README.md", "{") is None
        print("Self-test passed.")
        return 0
    base = argv[argv.index("--base") + 1] if "--base" in argv else "origin/main"
    kind_fails, kind_warns = check_kind(base)
    parse_fails, parse_warns = check_parse(base)
    problems = (check_owner() + check_decisions(base) + check_kit() + check_one_place(base) + check_finance(base)
                + kind_fails + check_roles() + check_handoff() + check_oracle() + check_decision_numbers(base)
                + check_purchase_ids(base) + parse_fails)
    for w in check_core_assets(base) + kind_warns + parse_warns:
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
