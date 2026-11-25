#!/usr/bin/env python3
"""Claude Code hooks: written agent rules made enforceable (ctlx-labs/firm policies/AGENT-RULES.md).

PreToolUse on the reply tools (mcp__hearthbot__post_message, mcp__hearthbot__request_decision,
mcp__slackbot__post_message, mcp__slackbot__reply):
  A. A question or a handoff to Ali names an AUTHORITY.md row that exists and is his (decision 0017: "Before any
     question to Ali, name the row of governance/AUTHORITY.md that makes it his").
     - A question: request_decision always; a post_message sentence ending in "?" that addresses Ali.
     - A handoff: a task put to Ali without a "?" ("please run", "you need to approve", a line opening "Run ...",
       "Type ...", "Approve ...").
     - The row must be an Action in governance/AUTHORITY.md (or the stamped .claude/authority-rows.json) whose
       "Who decides" names Ali. "AUTHORITY: n/a" does not count.
     - A decision card that repeats one still open in this session (same question, not closed with close_decision)
       is refused: ask once.
  B. Each sentence that claims done, merged, green, passed, fixed, verified, live, closed (and the other status words
     below) carries a link in that sentence or the next one, or says "not verified". One link no longer clears a
     whole reply.
  S. Scope ledger (review action 19): once a session has read or written a SCOPE.md, a turn opened by a person's
     message reads that file and writes the new agreement to it before the first reply, or the reply says
     "Scope: no change".
Stop:
  C. A turn that did work ends with a reply or a wake-up, and its last reply does not close on a promise ("Next I will
     ...") unless a wake-up is set in the same turn (Ali, 24 Nov: "a turn never ends on 'next I will'"). A promise
     that waits on Ali ("once you add the secret, I will ...") is allowed: his reply wakes the thread.
     In a project thread (the reply tools exist), both parts apply. In a Remote Control or other remote session with
     no reply tools, the last text of the turn is the reply, and only the promise part applies.

Fail safe: any error, an unreadable transcript, a missing field, or a second stop in a row (stop_hook_active) lets the
action through, so a bug in this file can never stall a thread. Switch off for one session: CTLX_HOOKS_OFF=1.
Blocking: PreToolUse returns permissionDecision "deny" with the reason; Stop returns decision "block" with the reason.
    python3 agent_rules.py --self-test
Stamped from ctlx-labs/claude settings/firm/hooks/.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys

REPLY_TOOLS = {"mcp__hearthbot__post_message", "mcp__hearthbot__request_decision",
               "mcp__slackbot__post_message", "mcp__slackbot__reply"}
QUESTION_TOOLS = {"mcp__hearthbot__request_decision"}
WAKE_TOOLS = {"mcp__claude-code-remote__send_later", "mcp__claude-code-remote__create_trigger", "ScheduleWakeup",
              "CronCreate"}
# A turn counts as answered if it ends with one of these: a reply, a decision card, a resolved thread, or a wake-up.
ANSWERED = REPLY_TOOLS | WAKE_TOOLS | {"mcp__hearthbot__set_thread_resolved"}
# Tools that are not work: reading, searching, and talking.
NOT_WORK = re.compile(r"^(Read|Grep|Glob|ToolSearch|Skill|TaskList|TaskGet|mcp__hearthbot__.*|"
                      r"mcp__github__(get|list|pull_request_read|issue_read).*)$")
WRITE_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}

AUTHORITY = re.compile(r"\bAUTHORITY(?:\.md)?\b\s*(?:row)?\s*[:\-–]\s*([^\n(;]{3,})", re.IGNORECASE)
TO_ALI = re.compile(r"\b(you|your|should I|shall I|can I|may I|do we|should we|ok to|okay to)\b", re.IGNORECASE)
HANDOFF_VERBS = r"(run|type|approve|click|paste|open|enter|sign in|log in|install|press|add|set|create|merge|send)"
HANDOFF = re.compile(
    rf"(\b(please|you('ll| will)? need to|you must|you should|you have to|you can now|asking you to|ask you to)\s+"
    rf"{HANDOFF_VERBS}\b)|(^\s*[-*]?\s*(Run|Type|Approve|Click|Paste|Open|Enter|Sign in|Log in|Install|Press)\b)",
    re.IGNORECASE | re.MULTILINE)
CLAIM = re.compile(r"\b(done|merged|green|passe[sd]|fixed|shipped|deployed|completed|resolved|closed|verified|"
                   r"confirmed|live|published|installed|enabled|configured|released|in place|up to date)\b",
                   re.IGNORECASE)
NEGATED = re.compile(r"\b(not|n't|never|no|nothing|isn't|wasn't|until|once|when|before|after|if|whether|to be)\b"
                     r"[^.?!\n]{0,40}$", re.IGNORECASE)
URL = re.compile(r"\[([^\]]*)\]\(([^)]*)\)|https?://[^\s)]*[^\s).,;:!?]|/mnt/project-files/[^\s)]*[^\s).,;:!?]|#cmsg_\w+")
NOT_VERIFIED = re.compile(r"not verified", re.IGNORECASE)
FUTURE = re.compile(r"^\W*(?:(?:next|then|now|after that|meanwhile|tomorrow|later)\b[\s,:]*)?"
                    r"(?:I(?:'ll| will| am going to| am about to| plan to)|I'm (?:going|about) to|next step\b|"
                    r"let me)\b", re.IGNORECASE)
WAITS_ON_ALI = re.compile(r"\b(once|when|after|if|as soon as) you\b|\byour (reply|answer|choice|go|yes)\b",
                          re.IGNORECASE)
SCOPE_NO_CHANGE = re.compile(r"scope:\s*no change", re.IGNORECASE)


# ---- text helpers ----------------------------------------------------------------------------------------------

def strip_quotes(text: str) -> str:
    """Quoted text and code are someone else's words, not a claim or a question."""
    return re.sub(r'"[^"\n]*"|“[^”]*”|`[^`]*`|^>.*$', "", text, flags=re.MULTILINE)


def words(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split())


def sentences(text: str) -> list[list[str]]:
    """Lines, each split into sentences. Links become the token LINK so their dots do not split a sentence."""
    text = URL.sub(lambda m: (m.group(1) or "") + " LINK ", text)
    return [[s for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()] for line in text.splitlines()]


def questions_to_ali(text: str) -> list[str]:
    bare = strip_quotes(text)
    found = re.findall(r"[^.!?\n]*\?", bare)
    return [s.strip() for s in found if TO_ALI.search(s)]


def handoffs_to_ali(text: str) -> list[str]:
    return [m.group(0).strip() for m in HANDOFF.finditer(strip_quotes(text))]


def unproven_claims(text: str) -> list[str]:
    """Claim sentences with no link in the sentence or the next one, and no 'not verified'."""
    out = []
    for line in sentences(strip_quotes(text)):
        for i, s in enumerate(line):
            near = s + " " + (line[i + 1] if i + 1 < len(line) else "")
            if "LINK" in near or NOT_VERIFIED.search(near):
                continue
            for m in CLAIM.finditer(s):
                if not NEGATED.search(s[:m.start()]):
                    out.append(s.strip())
                    break
    return out


def closes_on_promise(text: str) -> str | None:
    """The last sentence of the reply, if it promises work and does not wait on Ali."""
    lines = [ln for ln in sentences(strip_quotes(text)) if ln]
    if not lines:
        return None
    last = lines[-1][-1].strip()
    if FUTURE.search(last) and not WAITS_ON_ALI.search(last):
        return last
    return None


# ---- AUTHORITY rows ----------------------------------------------------------------------------------------------

def authority_rows() -> list[str] | None:
    """Actions that are Ali's, from governance/AUTHORITY.md, else the stamped .claude/authority-rows.json. None if
    neither is found (the existence check is then skipped)."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    md = os.path.join(root, "governance", "AUTHORITY.md")
    if os.path.exists(md):
        return rows_from_markdown(open(md, encoding="utf-8").read())
    js = os.path.join(root, ".claude", "authority-rows.json")
    if os.path.exists(js):
        return json.load(open(js, encoding="utf-8")).get("ali", [])
    return None


def rows_from_markdown(text: str) -> list[str]:
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and cells[0] != "Action" and not set(cells[0]) <= set("-: "):
            if re.search(r"\bAli\b", cells[1]):
                rows.append(cells[0])
    return rows


def cites_row(text: str, rows: list[str] | None) -> tuple[bool, str]:
    """(ok, cited). ok when an AUTHORITY line names an existing row of Ali's (or the row list is unavailable)."""
    cited = [m.group(1).strip(" .") for m in AUTHORITY.finditer(text)]
    if not cited:
        return False, ""
    if rows is None:
        return True, cited[0]
    for c in cited:
        cw = words(c)
        if len(cw) < 6 or cw in {"n a", "na", "none", "no row", "not applicable"}:
            continue
        for r in rows:
            rw = words(r)
            if rw.startswith(cw) or cw.startswith(rw) or difflib.SequenceMatcher(None, cw, rw[:len(cw) + 10]).ratio() >= 0.75:
                return True, c
    return False, cited[0]


# ---- transcript --------------------------------------------------------------------------------------------------

def load(path: str) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    return [e for e in entries if not e.get("isSidechain")]


def is_prompt(e: dict) -> bool:
    content = (e.get("message") or {}).get("content")
    is_result = isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
    return e.get("type") == "user" and not is_result and not e.get("isMeta")


def prompt_text(e: dict) -> str:
    content = (e.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content or [] if isinstance(b, dict))


def turn(entries: list[dict]) -> tuple[str, list[dict]]:
    """(prompt that opened the current turn, the assistant's blocks since then: tool_use and text, in order)."""
    blocks: list[dict] = []
    opener = ""
    for e in reversed(entries):
        if is_prompt(e):
            opener = prompt_text(e)
            break
        content = (e.get("message") or {}).get("content")
        if e.get("type") == "assistant" and isinstance(content, list):
            blocks[:0] = [b for b in content if isinstance(b, dict) and b.get("type") in ("tool_use", "text")]
    return opener, blocks


def all_tool_uses(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        content = (e.get("message") or {}).get("content")
        if e.get("type") == "assistant" and isinstance(content, list):
            out += [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
    return out


def has_reply_tools(path: str) -> bool:
    with open(path, encoding="utf-8") as f:
        return any("mcp__hearthbot__" in line or "mcp__slackbot__" in line for line in f)


def remote_session() -> bool:
    return os.environ.get("CLAUDE_CODE_REMOTE") == "true" or "remote" in os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")


def touches(call: dict, path: str) -> str:
    """'read', 'write' or '' for one tool call and the scope file."""
    name, ti = call.get("name", ""), call.get("input") or {}
    base = os.path.basename(path)
    target = str(ti.get("file_path") or ti.get("notebook_path") or "")
    if target and (target.endswith(path) or path.endswith(target)):
        return "write" if name in WRITE_TOOLS else "read" if name == "Read" else ""
    cmd = str(ti.get("command", ""))
    if name == "Bash" and path in cmd:
        return "write" if re.search(r">>?\s*\S*" + re.escape(base) + r"|sed -i|tee\b|python", cmd) else "read"
    return ""


def scope_file(calls: list[dict]) -> str | None:
    found = None
    for c in calls:
        ti = c.get("input") or {}
        p = str(ti.get("file_path") or "")
        if p.endswith("/SCOPE.md") or p == "SCOPE.md":
            found = p
    return found


# ---- checks ------------------------------------------------------------------------------------------------------

def ask_reason(kind: str, sample: str, cited: str) -> str:
    what = f"names '{cited[:60]}', which is not a row of Ali's in governance/AUTHORITY.md" if cited else \
        "names no governance/AUTHORITY.md row"
    return (f"Blocked by the firm's agent rules (decision 0017): this {kind} to Ali ('{sample[:100]}') {what}. "
            "Read decisions/ and AUTHORITY.md first; then add 'AUTHORITY: <the row's Action, as written> "
            "(<scope|money|outside the firm|one-way door|risk appetite>)' and name the decision the answer changes. "
            "No row of his: decide it yourself, log it, and tell him.")


def check_reply(tool: str, ti: dict, path: str = "", rows: list[str] | None = None) -> str | None:
    """Reason to deny, or None."""
    entries = load(path) if path and os.path.exists(path) else []
    if tool in QUESTION_TOOLS:
        text = " ".join(str(ti.get(k, "")) for k in ("question", "reason", "context"))
        text += " " + " ".join(str(o.get("consequence", "")) + " " + str(o.get("label", ""))
                               for o in ti.get("options") or [] if isinstance(o, dict))
        ok, cited = cites_row(text, rows)
        if not ok:
            return ask_reason("decision card", str(ti.get("question", "")), cited)
        dup = open_duplicate(str(ti.get("question", "")), entries)
        if dup:
            return ("Blocked by the firm's agent rules (ask once): a decision card with the same question is still "
                    f"open in this thread ('{dup[:100]}'). Wait for his answer, or close the old card with "
                    "close_decision first if the question has changed.")
        return None
    text = str(ti.get("text", ""))
    asks = questions_to_ali(text) + handoffs_to_ali(text)
    if asks:
        ok, cited = cites_row(text, rows)
        if not ok:
            return ask_reason("question or handoff", asks[0], cited)
    claims = unproven_claims(text)
    if claims:
        return ("Blocked by the firm's agent rules (no claim without proof): the sentence "
                f"'{claims[0][:120]}' states a result or status with no link beside it. Put the link to the PR, "
                "check run or file in that sentence, or write 'not verified' and name the check that would verify it.")
    if entries:
        reason = check_scope(entries, text)
        if reason:
            return reason
    return None


def open_duplicate(question: str, entries: list[dict]) -> str | None:
    q = words(question)
    if len(q) < 10:
        return None
    pending: list[str] = []
    for c in all_tool_uses(entries):
        if c.get("name") == "mcp__hearthbot__request_decision":
            pending.append(str((c.get("input") or {}).get("question", "")))
        elif c.get("name") == "mcp__hearthbot__close_decision":
            pending = pending[:-1]  # the card it closes is the most recent one in practice
    for p in pending:
        if difflib.SequenceMatcher(None, q, words(p)).ratio() >= 0.8:
            return p
    return None


def check_scope(entries: list[dict], text: str) -> str | None:
    calls = all_tool_uses(entries)
    path = scope_file(calls)
    if not path or SCOPE_NO_CHANGE.search(text):
        return None
    opener, blocks = turn(entries)
    if not re.search(r'trust="principal"', opener) and "<wake" in opener:
        return None  # not a person's message (a relay, a scheduled wake, a PR event)
    done = {touches(b, path) for b in blocks if b.get("type") == "tool_use"}
    if {"read", "write"} <= done:
        return None
    return ("Blocked by the firm's agent rules (scope ledger, review action 19): this thread keeps a scope ledger at "
            f"{path}. Before replying to Ali's message, read it and write his agreement (his words, the time, what "
            "it fixes) as a new row. If his message agrees nothing new, add the line 'Scope: no change' to the reply.")


def check_stop(event: dict) -> str | None:
    if event.get("stop_hook_active"):
        return None
    path = event.get("transcript_path") or ""
    if not path or not os.path.exists(path):
        return None
    thread = has_reply_tools(path)
    if not thread and not remote_session():
        return None
    _, blocks = turn(load(path))
    calls = [b for b in blocks if b.get("type") == "tool_use"]
    names = [c.get("name", "") for c in calls]
    woke = any(n in WAKE_TOOLS for n in names)
    if thread:
        worked = any(not NOT_WORK.match(n) for n in names)
        if worked and not any(n in ANSWERED for n in names):
            return ("Blocked by the firm's agent rules (Ali, 24 Nov: a thread never ends its turn with no one due to "
                    "wake it): this turn did work but sent no reply and set no wake-up. Post the result, or, if you "
                    "are waiting on a job or another thread, set a wake-up (send_later, at most 45 minutes ahead).")
        replies = [str((c.get("input") or {}).get("text", "")) for c in calls
                   if c.get("name") in REPLY_TOOLS - QUESTION_TOOLS]
        last = replies[-1] if replies else ""
    else:
        texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        last = texts[-1] if texts else ""
    promise = closes_on_promise(last)
    if promise and not woke:
        return ("Blocked by the firm's agent rules (Ali, 24 Nov: a turn never ends on 'next I will'): the reply "
                f"closes on '{promise[:100]}'. Do that step now, in this turn, or set a wake-up for it "
                "(send_later, at most 45 minutes ahead).")
    return None


def main() -> int:
    if os.environ.get("CTLX_HOOKS_OFF") == "1":
        return 0
    try:
        event = json.load(sys.stdin)
        name = event.get("hook_event_name", "")
        if name == "PreToolUse":
            tool = event.get("tool_name", "")
            if tool not in REPLY_TOOLS:
                return 0
            reason = check_reply(tool, event.get("tool_input") or {}, event.get("transcript_path") or "",
                                 authority_rows())
            if reason:
                json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": reason}}, sys.stdout)
        elif name == "Stop":
            reason = check_stop(event)
            if reason:
                json.dump({"decision": "block", "reason": reason}, sys.stdout)
    except Exception as exc:  # fail safe: never stall a thread on a bug here
        print(f"agent_rules.py skipped: {exc!r}", file=sys.stderr)
    return 0


# ---- self-test ---------------------------------------------------------------------------------------------------

def self_test() -> int:
    import subprocess
    import tempfile

    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "governance"))
    with open(os.path.join(d, "governance", "AUTHORITY.md"), "w") as f:
        f.write("| Action | Who decides | How |\n|---|---|---|\n"
                "| Create a repository | Ali (scope) | x |\n"
                "| Change a repository's visibility | Ali (made public) | x |\n"
                "| Push a branch | agent | auto |\n")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    def run(event: dict, extra_env: dict | None = None) -> dict:
        out = subprocess.run([sys.executable, __file__], input=json.dumps(event), capture_output=True, text=True,
                             env=dict(env, **(extra_env or {})))
        assert out.returncode == 0, out.stderr
        assert "skipped" not in out.stderr, out.stderr
        return json.loads(out.stdout) if out.stdout.strip() else {}

    def transcript(*items, opener: str = '<wake><message trust="principal">hi</message></wake> mcp__hearthbot__') -> str:
        """items: tool names, (tool name, input) pairs, or ('TEXT', text)."""
        p = os.path.join(d, f"t{len(os.listdir(d))}.jsonl")
        rows = [{"type": "user", "message": {"role": "user", "content": opener}}]
        for i, it in enumerate(items):
            name, ti = (it, {}) if isinstance(it, str) else it
            if name == "TEXT":
                rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "text", "text": ti}]}})
                continue
            rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": f"t{i}", "name": name, "input": ti}]}})
            rows.append({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"t{i}", "content": "ok"}]}})
        with open(p, "w") as f:
            f.write("\n".join(json.dumps(r) for r in rows) + "\n")
        return p

    def post(text: str, path: str = "") -> dict:
        return run({"hook_event_name": "PreToolUse", "tool_name": "mcp__hearthbot__post_message",
                    "tool_input": {"text": text}, "transcript_path": path})

    def card(ti: dict, path: str = "") -> dict:
        return run({"hook_event_name": "PreToolUse", "tool_name": "mcp__hearthbot__request_decision",
                    "tool_input": ti, "transcript_path": path})

    denied = lambda r: r.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    # A. questions to Ali name a real row of his.
    assert denied(post("Firm, step: hooks. Should I stamp every repository now?"))
    assert not denied(post("Firm, step: hooks. Should I make the repo public?\nAUTHORITY: Change a repository's "
                           "visibility (made public)."))
    assert denied(post("Should I make the repo public?\nAUTHORITY: n/a"))
    assert denied(post("Should I push the branch?\nAUTHORITY: Push a branch"))  # the agent's row, not Ali's
    assert not denied(post("Firm, step: notes. What is myralphloop? It is the firm's build method."))
    assert not denied(post('Ali asked "can you check the PR?" and I checked it: https://github.com/x/y/pull/1'))
    q = {"question": "Create a new repository for ESCO?", "options": [{"label": "Yes", "consequence": "x"}],
         "recommended": 0}
    assert denied(card(q))
    q["reason"] = "AUTHORITY: Create a repository (scope)."
    assert not denied(card(q))
    # A. handoffs without a "?"
    assert denied(post("Firm, step: token. Please add ONE_ENGINE_TOKEN in the baghara secrets and reply added."))
    assert denied(post("Firm, step: Mac.\nRun `brew install gitleaks` on the Mac."))
    assert not denied(post("Firm, step: Mac. Please add the secret.\nAUTHORITY: Create a repository (scope)"))
    assert not denied(post("Firm, step: hooks. Added the deny rules: https://github.com/x/y/pull/2"))
    # A. a card that repeats an open one
    p = transcript(("mcp__hearthbot__request_decision", {"question": "Create a new repository for ESCO?"}))
    assert denied(card(q, p))
    p = transcript(("mcp__hearthbot__request_decision", {"question": "Create a new repository for ESCO?"}),
                   ("mcp__hearthbot__close_decision", {"message_id": "cmsg_1"}))
    assert not denied(card(q, p))
    # B. each claim carries its own link
    assert denied(post("Firm, step: hooks. The PR is merged and the check is green."))
    assert not denied(post("Firm, step: hooks. Merged: https://github.com/ctlx-labs/claude/pull/52"))
    assert not denied(post("Firm, step: hooks. Merged. https://github.com/ctlx-labs/claude/pull/52"))
    assert denied(post("Firm, step: hooks. Merged: https://github.com/ctlx-labs/claude/pull/52. "
                       "The baghara secret is configured too."))
    assert denied(post("Firm, step: hooks. The rule is live on every repository."))
    assert not denied(post("Firm, step: hooks. Tests passed locally, not verified in CI (firm-check run)."))
    assert not denied(post("Firm, step: hooks. I will merge once the check is green."))
    assert not denied(post("Firm, step: hooks. Nothing is merged yet."))
    assert not denied(post("Firm, step: hooks. The [PR](https://github.com/x/y/pull/3) is merged."))
    # Other tools are never touched.
    assert not run({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "done?"}})
    # S. scope ledger
    sc = "/w/projects/x/SCOPE.md"
    p = transcript(("Read", {"file_path": sc}))
    with open(p) as f:
        prior = f.read()
    with open(p, "w") as f:  # an earlier turn read the ledger; a new message from Ali opens this turn
        f.write(prior + json.dumps({"type": "user", "message": {"role": "user", "content":
                '<wake><message trust="principal">yes, A4</message></wake>'}}) + "\n")
    assert denied(post("Firm, step: scope. Noted.", p))
    assert not denied(post("Firm, step: scope. Noted.\nScope: no change", p))
    with open(p, "a") as f:
        for i, (n, ti) in enumerate([("Read", {"file_path": sc}), ("Edit", {"file_path": sc})]):
            f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": f"s{i}", "name": n, "input": ti}]}}) + "\n")
    assert not denied(post("Firm, step: scope. Written as row 21.", p))
    p = transcript(("Read", {"file_path": sc}), opener="<wake><relay>coordinator note</relay></wake>")
    assert not denied(post("Firm, step: scope. Noted.", p))  # not a person's message
    # C. stop
    stop = lambda p, active=False, e=None: run({"hook_event_name": "Stop", "transcript_path": p,
                                                "stop_hook_active": active}, e)
    blocked = lambda r: r.get("decision") == "block"
    assert blocked(stop(transcript("Bash", "Edit", "mcp__hearthbot__no_reply_needed")))
    assert not stop(transcript("Bash", ("mcp__hearthbot__post_message", {"text": "Done: https://x.y/1"})))
    assert not stop(transcript("Bash", "mcp__claude-code-remote__send_later", "mcp__hearthbot__no_reply_needed"))
    assert not stop(transcript("Read", "mcp__hearthbot__no_reply_needed"))  # no work done
    assert not stop(transcript("Bash"), active=True)  # second stop in a row: let it end
    assert not stop(os.path.join(d, "missing.jsonl"))
    promise = ("mcp__hearthbot__post_message", {"text": "Firm, step: hooks. PR open. Next I will stamp the repos."})
    assert blocked(stop(transcript("Bash", promise)))
    assert not stop(transcript("Bash", promise, "mcp__claude-code-remote__send_later"))
    waits = ("mcp__hearthbot__post_message", {"text": "Firm, step: token. Once you add it, I will re-run the job."})
    assert not stop(transcript("Bash", waits))
    plain = transcript("Bash", ("TEXT", "Edited. Next I will run the tests."), opener="plain session")
    assert not stop(plain)  # a local session with no reply tools: not checked
    assert blocked(stop(plain, e={"CLAUDE_CODE_REMOTE": "true"}))  # a remote session: the promise counts
    assert not stop(transcript("Bash", ("TEXT", "Tests pass: https://x.y/run/1"), opener="plain session"),
                    e={"CLAUDE_CODE_REMOTE": "true"})
    # Fail safe: garbage in, nothing blocked.
    out = subprocess.run([sys.executable, __file__], input="not json", capture_output=True, text=True, env=env)
    assert out.returncode == 0 and not out.stdout.strip()
    print("Self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv else main())
