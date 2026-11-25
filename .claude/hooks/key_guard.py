#!/usr/bin/env python3
"""Claude Code PreToolUse hook: deploy keys and repository secrets are logged, temporary, read-only and wired right.

Ali, 25 Nov 2026: "can we do that permission temporary? should we remove the access every now and then? for the
connect repo to the wrong place, can we have something that checks that?"

Bash commands `gh repo deploy-key add` and `gh secret set` are allowed only when:
1. The command names a row of ctlx-labs/firm ops/access-keys.csv by its id (K01, K02, ...): in `--title` for a deploy
   key, or as a trailing `# K07` comment. The row is read from firm main, so it is logged before the key exists.
2. The row's kind matches (deploy_key or secret), its target (deploy key) or consumer (secret) is the `-R` repository,
   its status is active, and its expiry is a date no more than 90 days after it was created and not yet passed.
3. A deploy key is read-only unless the row says access=write; `--allow-write` with access=read is blocked.
4. The wiring check passes (`wiring_problems`): a public repository never gets a key to a private one; write access
   needs a purpose in the row; the consumer may read the target only when the catalogs link them: the target is a
   library (spec.type library), or both are in the same system, or the consumer's spec.dependsOn names the target.
The same check runs in the weekly sweep (ctlx-labs/firm ops/tools/key_sweep.py, ROLES row 7).
Exit code 2 blocks and shows the reason. When GitHub cannot be read, the command is blocked (fail closed).
    python3 key_guard.py --self-test
Stamped from ctlxholdings/claude settings/firm/hooks/.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import re
import shlex
import subprocess
import sys
from datetime import date

ORG = "ctlx-labs"
LOG = "ops/access-keys.csv"
MAX_DAYS = 90
KEY_ID = re.compile(r"\bK\d{2,}\b")
FIELDS = ["id", "kind", "consumer", "target", "access", "purpose", "created", "expires", "thread", "status"]


def catalog_info(text: str) -> dict:
    """spec.type, spec.system and spec.dependsOn of the Component in a catalog-info.yaml (no YAML library)."""
    out = {"type": "", "system": "", "dependsOn": []}
    doc = text.split("\n---")[0]
    in_spec = in_dep = False
    for line in doc.splitlines():
        if re.match(r"^spec:\s*$", line):
            in_spec = True
            continue
        if in_spec and re.match(r"^\S", line):
            in_spec = False
        if not in_spec:
            continue
        m = re.match(r"^  (type|system):\s*['\"]?([^'\"#]+?)['\"]?\s*(#.*)?$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
            in_dep = False
            continue
        m = re.match(r"^  dependsOn:\s*(\[(.*)\])?\s*$", line)
        if m:
            in_dep = m.group(1) is None
            if m.group(2):
                out["dependsOn"] += [x.strip(" '\"") for x in m.group(2).split(",") if x.strip()]
            continue
        m = re.match(r"^\s+-\s*['\"]?([^'\"#]+?)['\"]?\s*$", line)
        if in_dep and m:
            out["dependsOn"].append(m.group(1))
        elif re.match(r"^  \S", line):
            in_dep = False
    out["dependsOn"] = [d.split(":")[-1].split("/")[-1] for d in out["dependsOn"]]
    return out


def wiring_problems(row: dict, consumer: dict, target: dict, consumer_private: bool, target_private: bool) -> list:
    """Why this key wires the wrong places; empty when the wiring is allowed. consumer and target: catalog_info()."""
    p = []
    if target_private and not consumer_private:
        p.append(f"public {row['consumer']} would get access to private {row['target']}")
    if row.get("access") == "write" and len(row.get("purpose", "").split()) < 4:
        p.append("write access needs a purpose in the row saying why read is not enough")
    if row.get("access") not in ("read", "write"):
        p.append(f"access must be read or write, not {row.get('access')!r}")
    linked = (target.get("type") == "library"
              or (target.get("system") and target.get("system") == consumer.get("system"))
              or row["target"] in consumer.get("dependsOn", []))
    if not linked:
        p.append(f"the catalogs do not link {row['consumer']} to {row['target']}: the target is not a library, not in "
                 f"the same system, and not in {row['consumer']}'s spec.dependsOn")
    return p


def row_problems(row: dict | None, kind: str, repo: str, today: date) -> list:
    if row is None:
        return [f"no row with that id in ctlx-labs/firm {LOG} on main; add the row by PR first"]
    p = []
    if row.get("kind") != kind:
        p.append(f"row {row['id']} is kind {row.get('kind')}, not {kind}")
    side = "target" if kind == "deploy_key" else "consumer"
    if row.get(side) != repo:
        p.append(f"row {row['id']} names {side} {row.get(side)}, not {repo}")
    if row.get("status") != "active":
        p.append(f"row {row['id']} has status {row.get('status')}, not active")
    try:
        created, expires = date.fromisoformat(row["created"]), date.fromisoformat(row["expires"])
        if (expires - created).days > MAX_DAYS:
            p.append(f"row {row['id']} expires more than {MAX_DAYS} days after it was created")
        if expires < today:
            p.append(f"row {row['id']} expired on {expires}")
    except (KeyError, ValueError):
        p.append(f"row {row['id']} needs created and expires dates (YYYY-MM-DD)")
    return p


def parse_command(cmd: str) -> dict | None:
    """{kind, repo, key_id, allow_write} for a deploy-key add or secret set command, else None."""
    m = re.search(r"\bgh\s+(repo\s+deploy-key\s+add|secret\s+set)\b(.*)", cmd, re.S)
    if not m:
        return None
    kind = "deploy_key" if "deploy-key" in m.group(1) else "secret"
    rest = m.group(2).split("\n")[0]
    comment = rest.split("#", 1)[1] if "#" in rest else ""
    try:
        args = shlex.split(rest.split("#", 1)[0].split("&&")[0].split(";")[0].split("|")[0])
    except ValueError:
        args = rest.split()
    repo = title = ""
    for i, a in enumerate(args):
        if a in ("-R", "--repo") and i + 1 < len(args):
            repo = args[i + 1]
        elif a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        elif a in ("-t", "--title") and i + 1 < len(args):
            title = args[i + 1]
        elif a.startswith("--title="):
            title = a.split("=", 1)[1]
    ids = KEY_ID.findall(title + " " + comment)
    return {"kind": kind, "repo": repo.split("/")[-1], "key_id": ids[0] if ids else "",
            "allow_write": "--allow-write" in args or "-w" in args}


def gh(path: str):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise RuntimeError(f"gh api {path}: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout)


def read_file(repo: str, path: str) -> str:
    return base64.b64decode(gh(f"repos/{ORG}/{repo}/contents/{path}")["content"]).decode()


def log_rows(text: str) -> dict:
    return {r["id"]: r for r in csv.DictReader(io.StringIO(text)) if r.get("id")}


def check(cmd: str, today: date | None = None, fetch=None) -> list:
    """Problems with this command; empty means allowed. fetch(repo, path) and gh() are replaced in the self-test."""
    c = parse_command(cmd)
    if c is None:
        return []
    today = today or date.today()
    if not c["repo"]:
        return ["name the repository with -R ctlx-labs/<repo>"]
    if not c["key_id"]:
        return [f"name the {LOG} row: --title 'K07 <consumer> reads <target>' or a trailing '# K07'"]
    fetch = fetch or read_file
    row = log_rows(fetch("firm", LOG)).get(c["key_id"])
    p = row_problems(row, c["kind"], c["repo"], today)
    if row is None:
        return p
    if c["kind"] == "deploy_key" and c["allow_write"] and row.get("access") != "write":
        p.append(f"--allow-write but row {row['id']} says access={row.get('access')}; deploy keys are read-only")
    cons, targ = (catalog_info(fetch(r, "catalog-info.yaml")) for r in (row["consumer"], row["target"]))
    priv = {r: fetch(r, "@private") == "true" for r in (row["consumer"], row["target"])}
    return p + wiring_problems(row, cons, targ, priv[row["consumer"]], priv[row["target"]])


def live_fetch(repo: str, path: str) -> str:
    if path == "@private":
        return "true" if gh(f"repos/{ORG}/{repo}").get("private") else "false"
    return read_file(repo, path)


def self_test() -> None:
    log = ("id,kind,consumer,target,access,purpose,created,expires,thread,status\n"
           "K01,deploy_key,01-averta,one-engine,read,CI installs the engine,2026-11-25,2026-12-25,t,active\n"
           "K02,secret,01-averta,one-engine,read,CI installs the engine,2026-11-25,2026-12-25,t,active\n"
           "K03,deploy_key,website,deal-kit,read,x,2026-11-25,2026-12-25,t,active\n"
           "K04,deploy_key,01-averta,one-engine,read,x,2026-11-25,2027-06-01,t,active\n"
           "K05,deploy_key,deal-nle,deal-kit,write,x,2026-11-25,2026-12-01,t,active\n")
    files = {
        ("firm", LOG): log,
        ("one-engine", "catalog-info.yaml"): "kind: Component\nspec:\n  type: library\n  system: one-engine\n",
        ("01-averta", "catalog-info.yaml"): "kind: Component\nspec:\n  type: application\n  system: averta\n",
        ("website", "catalog-info.yaml"): "kind: Component\nspec:\n  type: website\n  system: website\n",
        ("deal-kit", "catalog-info.yaml"): "kind: Component\nspec:\n  type: service\n  system: deal-machine\n",
        ("deal-nle", "catalog-info.yaml"): ("kind: Component\nspec:\n  type: data\n  system: deals\n"
                                            "  dependsOn:\n    - component:deal-kit\n"),
        ("website", "@private"): "false", ("01-averta", "@private"): "true", ("one-engine", "@private"): "true",
        ("deal-kit", "@private"): "true", ("deal-nle", "@private"): "true",
    }
    f = lambda r, p: files[(r, p)]  # noqa: E731
    t = date(2026, 11, 26)
    ok = "gh repo deploy-key add k.pub -R ctlx-labs/one-engine --title 'K01 01-averta reads one-engine'"
    assert check(ok, t, f) == [], check(ok, t, f)
    assert check("gh secret set ENGINE_KEY -R ctlx-labs/01-averta < k  # K02", t, f) == []
    assert check("ls -la", t, f) == []
    assert check("gh repo deploy-key add k.pub -R ctlx-labs/one-engine", t, f)            # no row id
    assert check(ok + " --allow-write", t, f)                                               # write on a read row
    assert any("public" in x for x in check(
        "gh repo deploy-key add k.pub -R ctlx-labs/deal-kit -t K03", t, f))               # public -> private
    assert any("link" in x for x in check(
        "gh repo deploy-key add k.pub -R ctlx-labs/deal-kit -t K03", t, f))               # not linked
    assert any("90 days" in x for x in check(
        "gh repo deploy-key add k.pub -R ctlx-labs/one-engine -t K04", t, f))
    assert any("purpose" in x for x in check(
        "gh repo deploy-key add k.pub -R ctlx-labs/deal-kit -t K05 --allow-write", t, f))  # write, no reason
    assert not any("link" in x for x in check(
        "gh repo deploy-key add k.pub -R ctlx-labs/deal-kit -t K05", t, f))               # dependsOn links
    assert check(ok, date(2027, 1, 1), f)                                                    # expired
    assert check("gh repo deploy-key add k.pub -R ctlx-labs/one-engine -t K09", t, f)       # no such row
    print("Self-test passed.")


def main(argv: list) -> int:
    if "--self-test" in argv:
        self_test()
        return 0
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    cmd = (data.get("tool_input") or {}).get("command", "")
    if parse_command(cmd) is None:
        return 0
    try:
        problems = check(cmd, fetch=live_fetch)
    except Exception as e:  # noqa: BLE001 - fail closed: a key is not made unchecked
        problems = [f"could not run the check ({e}); the key is not created unchecked"]
    if problems:
        print("Blocked by key_guard.py (deploy keys and secrets, ctlx-labs/firm ops/access-keys.csv):\n- "
              + "\n- ".join(problems), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
