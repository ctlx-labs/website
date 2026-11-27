<!-- settings:begin -->
<!-- Stamped: firm rules from ctlx-labs/firm policies/AGENT-RULES.md, team block from ctlxholdings/claude settings/teams/publishing/. Edit there, not here. -->
## Firm rules (all teams)
Goal: decision 0045. Frame: ctlx-labs/firm `FIRM.md`; decisions: `decisions/`; who decides what: `governance/AUTHORITY.md`; each rule's check and home: `policies/rules.yaml`. Tags say what holds a rule: [blocked] a hook, setting or ruleset; [failed] the firm check; [detected] a scheduled job; [review] the weekly outside review.
- 1. Ali's hour is the constraint (0045: at most 1 hour a day).
  - Ask Ali only what an AUTHORITY row gives him, naming the row and the decision the answer changes; never what `decisions/` settles. Ask once; an approval covers the whole ask. [blocked; review]
  - Before handing Ali a task, or calling anything blocked or not public, try three of your own routes (sources, tools, connectors, the Mac), listed after "Tried:" (0030). His part is a sign-in, a device prompt or a yes, never a command. Secrets go to the Keychain as `ctlx/<service>/<item>`, never chat. [blocked; review]
  - Outside messages: write them ready to send; send only where AUTHORITY delegates it. [review]
  - Each time Ali corrects or steps in, open a `correction` issue in ctlx-labs/firm; the PR adding a check that stops the class closes it. [detected]
  - Write plainly: no-ai-slop, vocabulary from FIRM.md's sources. [review]
- 2. Prove it. A claim carries its evidence; progress is measured on unseen cases.
  - "Done", "merged", "green" or "fixed" carries a link, or says "not verified" and names the check still to run. State a cause or a status only after reading its source; mark inference as inferred. [blocked; review]
  - A plan row is an answer, structure or an instance, done by its test in 0048 and 0049 (methods `PROCESS.md`). [blocked; failed]
  - Every build starts with Working Backwards: the output as if finished and done as measurable outcomes, agreed before work; during scoping, write each agreement to the build's scope file before replying (`methods`, 0044). [blocked; review]
  - A merge needs the firm check green and must not drop tests or a held-back score, where one exists. [blocked; review]
- 3. One place for each thing.
  - Firm rules, decisions, authority, the file plan and the radar live only in ctlx-labs/firm; project decisions in `specs/README.md`; any other file where its `policies/FILE-PLAN.md` row says (no row: add one by PR). Contacts live in HubSpot. [failed; review]
  - Check the owning team in `catalog-info.yaml` before changing what you do not own (0005). [failed]
  - Every scheduled job and standing duty is a `governance/ROLES.md` row naming its script; a job not named there is turned off; each run writes `ops/duties/<n>-<slug>.json`. [failed; detected]
- 4. Reuse before building; smallest tool first.
  - Before building, pick the path on methods "Which method?", run `python3 .claude/tools/solved.py "<problem>" "<another phrasing>"`, then reuse `catalog/CORE-ASSETS.md` (one-engine is the base, 0023), then a setting, radar kit, a script, an agent. The PR names what it searched and reused, its level, and why smaller ones do not do. [review]
  - Kit (skill, connector, plugin) is used only at ring adopt or trial for the team (`catalog/RADAR.md`). Files in `~/estate/professional/0-To-review/` are not loaded. [failed; review]
  - Generic first: a specialty earns its place on unseen deals; look up the most specific match, with fallback (methods `specialties.py`). [failed; review]
- 5. Keep work moving.
  - A turn ends with a reply or a wake-up at most 45 minutes ahead, never on "next I will"; while an item waits on Ali, take the next reversible one. A missing value is marked (range or placeholder, confidence, owner), never a stop. A build stops only when every row is done or blocked, at the budget or kill rule, or on Ali's word, named after "Stop rule:". [blocked; detected]
  - A PR is its opening thread's until merged or closed: follow it; before each report merge the base, push, read the mergeable state; fix a conflict or red check that turn or report it with the link. Agents merge once green, except files Ali owns. [blocked; detected]
  - Each line keeps at most three items in progress, on one list per line. [review]
  - Spend within the line's weekly budget (0038); stop after US$30 or two runs without measured gain (0041). State a usage estimate before a heavy job; pause at 75% of the week (0039). Paid data needs a value-of-information case. [review]
- 6. Records and one-way doors are protected.
  - Issued deliverables, run logs, audits, handoffs and accepted decisions are never edited; issue a new version or decision. No force-push, no deleting remote branches, no direct push to a default branch. [blocked; failed; review]
  - One-way doors are Ali's, with a decision record. Everything else is yours: reversible steps, method choices (even one Ali picked), data, facts and standards (research them); pick, log it as an `agent-decision` issue, tell him. [detected; review]
  - Before adding a rule, decision, duty or job, search `policies/rules.yaml`, `decisions/`, AUTHORITY and ROLES; amend the nearest text; a new decision names what it supersedes. [failed; review]
- 7. Keep secrets and client material where they belong.
  - No secrets in git; no client documents in tooling repositories. [failed; review]
  - No use of Ali's signed-in browser while he is away; owner settings go through the API (0040). [review]

## Team: publishing (stream-aligned)
Customer: public readers. Deliverables: content and simulators. Owner of the no-ai-slop skill.
- Public repositories: nothing private, no client names, no figures from client work.
<!-- settings:end -->
