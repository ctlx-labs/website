#!/usr/bin/env python3
"""Claude Code hooks: three written agent rules made enforceable (ctlx-labs/firm policies/AGENT-RULES.md).

PreToolUse on the reply tools (mcp__hearthbot__post_message, mcp__hearthbot__request_decision,
mcp__slackbot__post_message, mcp__slackbot__reply):
  A. A question to Ali must name its AUTHORITY.md row (decision 0017: "Before any question to Ali, name the row of
     governance/AUTHORITY.md that makes it his"). request_decision is always a question; a post_message is one when a
     sentence ending in "?" addresses Ali ("you", "your", "should I", "shall I", "can I", "do we").
  B. A reply that claims done, merged, green, passed or fixed must carry a link ("No claim without proof: done means a
     check is green, with a link"), or say "not verified".
Stop:
  C. A turn that did work (any tool other than reads and reply tools) must end with a reply or a wake-up
     (AGENT-RULES, Ali 24 Nov: "a turn never ends on 'next I will'"). Applies only where the reply tools exist
     (a project thread); a plain Claude Code session is not checked.

Fail safe: any error, an unreadable transcript, a missing field, or a second stop in a row (stop_hook_active) lets the
action through, so a bug in this file can never stall a thread. Switch off for one session: CTLX_HOOKS_OFF=1.
Blocking: PreToolUse returns permissionDecision "deny" with the reason; Stop returns decision "block" with the reason.
    python3 agent_rules.py --self-test
Stamped from ctlx-labs/claude settings/firm/hooks/.
"""
from __future__ import annotations

import json
import os
import re
import sys

REPLY_TOOLS = {"mcp__hearthbot__post_message", "mcp__hearthbot__request_decision",
               "mcp__slackbot__post_message", "mcp__slackbot__reply"}
QUESTION_TOOLS = {"mcp__hearthbot__request_decision"}
# A turn counts as answered if it ends with one of these: a reply, a decision card, a resolved thread, or a wake-up.
ANSWERED = REPLY_TOOLS | {"mcp__hearthbot__set_thread_resolved", "mcp__claude-code-remote__send_later",
                          "mcp__claude-code-remote__create_trigger", "ScheduleWakeup", "CronCreate"}
# Tools that are not work: reading, searching, and talking.
NOT_WORK = re.compile(r"^(Read|Grep|Glob|ToolSearch|Skill|TaskList|TaskGet|mcp__hearthbot__.*|"
                      r"mcp__github__(get|list|pull_request_read|issue_read).*)$")

AUTHORITY = re.compile(r"\bAUTHORITY(\.md)?\b[^\n]{3,}", re.IGNORECASE)
TO_ALI = re.compile(r"\b(you|your|should I|shall I|can I|may I|do we|should we|ok to|okay to)\b", re.IGNORECASE)
CLAIM = re.compile(r"\b(done|merged|green|passe[sd]|fixed|shipped|deployed|completed)\b", re.IGNORECASE)
NEGATED = re.compile(r"\b(not|n't|never|no|nothing|isn't|wasn't|until|once|when|before|after|if)\b[^.?!\n]{0,40}$",
                     re.IGNORECASE)
LINK = re.compile(r"https?://|\]\((/|#|\.)|/mnt/project-files/|#cmsg_")
NOT_VERIFIED = re.compile(r"not verified", re.IGNORECASE)


def strip_quotes(text: str) -> str:
    """Quoted text and code are someone else's words, not a claim or a question."""
    return re.sub(r'"[^"\n]*"|“[^”]*”|`[^`]*`|^>.*$', "", text, flags=re.MULTILINE)


def questions_to_ali(text: str) -> list[str]:
    bare = strip_quotes(text)
    sentences = re.findall(r"[^.!?\n]*\?", bare)
    return [s.strip() for s in sentences if TO_ALI.search(s)]


def unproven_claims(text: str) -> list[str]:
    if LINK.search(text) or NOT_VERIFIED.search(text):
        return []
    out = []
    for m in CLAIM.finditer(strip_quotes(text)):
        before = strip_quotes(text)[max(0, m.start() - 60):m.start()]
        if not NEGATED.search(before):
            out.append(m.group(0))
    return out


def check_reply(tool: str, ti: dict) -> str | None:
    """Reason to deny, or None."""
    if tool in QUESTION_TOOLS:
        text = " ".join(str(ti.get(k, "")) for k in ("question", "reason", "context"))
        text += " " + " ".join(str(o.get("consequence", "")) + " " + str(o.get("label", ""))
                               for o in ti.get("options") or [] if isinstance(o, dict))
        if not AUTHORITY.search(text):
            return ("Blocked by the firm's agent rules (decision 0017): a decision card is a question to Ali, and it "
                    "must name the governance/AUTHORITY.md row that makes it his (scope, money, outside the firm, "
                    "one-way door, risk appetite), for example in `reason`: 'AUTHORITY: Create a repository (scope)'. "
                    "No row: decide it yourself, log it, and tell him.")
        return None
    text = str(ti.get("text", ""))
    asks = questions_to_ali(text)
    if asks and not AUTHORITY.search(text):
        return ("Blocked by the firm's agent rules (decision 0017): this reply asks Ali "
                f"'{asks[0][:100]}' without naming the governance/AUTHORITY.md row that makes it his. Add a line "
                "'AUTHORITY: <row> (<scope|money|outside the firm|one-way door|risk appetite>)', or, with no row, "
                "decide it yourself and say what you decided.")
    claims = unproven_claims(text)
    if claims:
        return ("Blocked by the firm's agent rules (no claim without proof): this reply says "
                f"'{claims[0]}' but carries no link. Add the link to the PR, check run or file, or write "
                "'not verified'.")
    return None


def read_turn(path: str) -> list[dict]:
    """Tool calls the main agent made since the last prompt (a person's message or a wake). [] if unreadable."""
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    calls: list[dict] = []
    for e in reversed(entries):
        if e.get("isSidechain"):
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        if e.get("type") == "user":
            is_result = isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
            if not is_result and not e.get("isMeta"):
                break  # the prompt that opened this turn
            continue
        if e.get("type") == "assistant" and isinstance(content, list):
            calls.extend(b for b in content if isinstance(b, dict) and b.get("type") == "tool_use")
    return list(reversed(calls))


def has_reply_tools(path: str) -> bool:
    with open(path, encoding="utf-8") as f:
        return any("mcp__hearthbot__" in line or "mcp__slackbot__" in line for line in f)


def check_stop(event: dict) -> str | None:
    if event.get("stop_hook_active"):
        return None
    path = event.get("transcript_path") or ""
    if not path or not os.path.exists(path) or not has_reply_tools(path):
        return None
    calls = read_turn(path)
    names = [c.get("name", "") for c in calls]
    worked = any(not NOT_WORK.match(n) for n in names)
    if not worked or any(n in ANSWERED for n in names):
        return None
    return ("Blocked by the firm's agent rules (Ali, 24 Nov: a thread never ends its turn with no one due to wake "
            "it): this turn did work but sent no reply and set no wake-up. Post the result, or, if you are waiting "
            "on a job or another thread, set a wake-up (send_later, at most 45 minutes ahead) before ending.")


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
            reason = check_reply(tool, event.get("tool_input") or {})
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


def self_test() -> int:
    import subprocess
    import tempfile

    def run(event: dict) -> dict:
        out = subprocess.run([sys.executable, __file__], input=json.dumps(event), capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout) if out.stdout.strip() else {}

    def post(text: str) -> dict:
        return run({"hook_event_name": "PreToolUse", "tool_name": "mcp__hearthbot__post_message",
                    "tool_input": {"text": text}})

    denied = lambda r: r.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    # A. questions to Ali
    assert denied(post("Firm, step: hooks. Should I stamp every repository now?"))
    assert not denied(post("Firm, step: hooks. Should I make the repo public?\nAUTHORITY: Change a repository's "
                           "visibility (made public)."))
    assert not denied(post("Firm, step: notes. What is myralphloop? It is the firm's build method."))
    assert not denied(post('Ali asked "can you check the PR?" and I checked it: https://github.com/x/y/pull/1'))
    card = {"question": "Create a new repository for ESCO?", "options": [{"label": "Yes", "consequence": "x"}],
            "recommended": 0}
    assert denied(run({"hook_event_name": "PreToolUse", "tool_name": "mcp__hearthbot__request_decision",
                       "tool_input": card}))
    card["reason"] = "AUTHORITY: Create a repository (scope)."
    assert not denied(run({"hook_event_name": "PreToolUse", "tool_name": "mcp__hearthbot__request_decision",
                           "tool_input": card}))
    # B. claims need a link
    assert denied(post("Firm, step: hooks. The PR is merged and the check is green."))
    assert not denied(post("Firm, step: hooks. Merged: https://github.com/ctlx-labs/claude/pull/52"))
    assert not denied(post("Firm, step: hooks. Tests passed locally, not verified in CI."))
    assert not denied(post("Firm, step: hooks. I will merge once the check is green."))
    assert not denied(post("Firm, step: hooks. Nothing is merged yet."))
    # Other tools are never touched.
    assert not run({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "done?"}})
    # C. stop with work and no reply
    with tempfile.TemporaryDirectory() as d:
        def transcript(*tools: str) -> str:
            p = os.path.join(d, "t.jsonl")
            rows = [{"type": "user", "message": {"role": "user", "content": "wake mcp__hearthbot__ x"}}]
            for i, t in enumerate(tools):
                rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": f"t{i}", "name": t, "input": {}}]}})
                rows.append({"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": f"t{i}", "content": "ok"}]}})
            with open(p, "w") as f:
                f.write("\n".join(json.dumps(r) for r in rows) + "\n")
            return p
        stop = lambda p, active=False: run({"hook_event_name": "Stop", "transcript_path": p,
                                            "stop_hook_active": active})
        assert stop(transcript("Bash", "Edit", "mcp__hearthbot__no_reply_needed")).get("decision") == "block"
        assert not stop(transcript("Bash", "mcp__hearthbot__post_message"))
        assert not stop(transcript("Bash", "mcp__claude-code-remote__send_later", "mcp__hearthbot__no_reply_needed"))
        assert not stop(transcript("Read", "mcp__hearthbot__no_reply_needed"))  # no work done
        assert not stop(transcript("Bash"), active=True)  # second stop in a row: let it end
        assert not stop(os.path.join(d, "missing.jsonl"))
        p = transcript("Bash")
        with open(p) as f:
            plain = f.read().replace("mcp__hearthbot__ x", "plain session")
        with open(p, "w") as f:
            f.write(plain)
        assert not stop(p)  # not a project thread
    # Fail safe: garbage in, nothing blocked.
    out = subprocess.run([sys.executable, __file__], input="not json", capture_output=True, text=True)
    assert out.returncode == 0 and not out.stdout.strip()
    print("Self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv else main())
