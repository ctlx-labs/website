<!-- settings:begin -->
<!-- Stamped: firm rules from ctlx-labs/firm policies/AGENT-RULES.md, team block from ctlxholdings/claude settings/teams/publishing/. Edit there, not here. -->
## Firm rules (all teams)
Goal: decision 0045. Frame: ctlx-labs/firm `FIRM.md`; decisions: `decisions/`; who decides what: `governance/AUTHORITY.md`; each rule's check and home: `policies/rules.yaml`. Tags say what holds a rule: [blocked] a hook, setting or ruleset; [failed] the firm check; [detected] a scheduled job; [review] the weekly outside review.
- 1. Ali's hour is the constraint (0045: at most 1 hour a day).
  - Before asking, read `decisions/` and AUTHORITY; do not ask what is settled. Ask only what an AUTHORITY row gives Ali, naming the row; a line with no budget has budget zero; a risk-appetite ask names the limit it changes. Ask once; an approval covers the whole ask. The ask names the decision the answer changes; drop a point that changes none. [blocked; review]
  - Everything else is yours: reversible steps, method choices (even one Ali picked), which example or data, facts and standards (research them). Pick, log it, tell him. [review]
  - Before handing Ali a task, or calling anything blocked or not public, try three of your own routes (sources, tools, connectors, the Mac), listed after "Tried:" (0030). Never ask him to run a command or type one; his part is a sign-in, a device prompt or a yes; a yes for a step on the Mac is asked once in words he types (quote them), never by decision card first (#250). Secrets go through one hidden-input macOS dialog to the Keychain as `ctlx/<service>/<item>`, never chat. [blocked; review]
  - Outside messages: write them ready to send; send only where AUTHORITY delegates it. [review]
  - Each time Ali corrects or steps in, open a `correction` issue in ctlx-labs/firm; the PR adding a check that stops the class closes it. [detected]
  - Write plainly: no-ai-slop, vocabulary from FIRM.md's sources. [review]
- 2. Prove it. A claim carries its evidence; progress is measured on unseen cases.
  - "Done", "merged", "green" or "fixed" carries a link, or says "not verified" and names the check still to run. State a cause or a status only after reading its source; mark inference as inferred. [blocked; review]
  - A plan row is an answer, structure or an instance (0048). Done: an answer cites its source, as a value or, where no exact figure is published, a range with a confidence label; structure passes its tests on marked inputs and is validated in parts (0049); an instance has a sourced real value for every marked input. [blocked; failed]
  - Every build starts with Working Backwards: the output as if finished and done as measurable outcomes, agreed before work; during scoping, write each agreement to the build's scope file before replying (`methods`, 0044). [blocked; review]
  - A repository with `specs/README.md` names its oracle ("Oracle: outside" or "Oracle: graded"). [failed]
  - Merging needs the firm check green; tests and a held-back score, where one exists, must not drop. [blocked; review]
- 3. One place for each thing.
  - Firm rules, decisions, authority, the file plan and the radar live only in ctlx-labs/firm; project decisions in the project's `specs/README.md`. [failed]
  - Write each file where its `policies/FILE-PLAN.md` row says; no row, add one by PR. Contacts live in HubSpot. [review]
  - Every repository has one owning team in `catalog-info.yaml` (0005); check it before changing what you do not own. [failed]
  - Every scheduled job and standing duty is a `governance/ROLES.md` row naming its script; a job not named there is turned off; each run writes `ops/duties/<n>-<slug>.json`. [failed; detected]
- 4. Reuse before building; smallest tool first.
  - Choose the path on ctlx-labs/methods "Which method?" first. [review]
  - Before building, run `python3 .claude/tools/solved.py "<problem>" "<another phrasing>"`; then reuse `catalog/CORE-ASSETS.md` (one-engine is the base, 0023), then a setting, then radar kit, then a script, then an agent. The PR names what it searched, what it reused, its level and why smaller ones do not do. [review]
  - Kit (skill, connector, plugin) is used only at ring adopt or trial for the team (`catalog/RADAR.md`). Files in `~/estate/professional/0-To-review/` are not loaded. [failed; review]
- 5. Keep work moving.
  - A turn ends with a reply or a wake-up at most 45 minutes ahead; never on "next I will". An item waiting on Ali yields to the next reversible item; never idle. Restart a parked Mac session with `start_remote_control`. [blocked; detected]
  - A missing value never stops a build: mark it (range or placeholder, confidence, source or owner). A build stops only when every row is done or blocked, at the budget or kill rule, or on Ali's word; the reply says which after "Stop rule:". [blocked]
  - A PR is its opening thread's until merged or closed: follow it; before each report merge the base, push, read the mergeable state; fix a conflict or red check that turn or report it with the link. Agents merge once green, except files Ali owns. [blocked; detected]
  - Each line keeps at most three items in progress, on one list per line. [review]
  - Spend within the line's weekly budget (0038); stop after US$30 or two runs without measured gain and follow the remedy ladder (0041). State a usage estimate before a heavy job; pause at 75% of the week (0039). Paid data needs a value-of-information case. [review]
- 6. Records and one-way doors are protected.
  - Issued deliverables, run logs, audits, handoffs and accepted decisions are never edited; issue a new version or decision. [blocked; failed; review]
  - One-way doors are Ali's, with a decision record; two-way doors are yours, logged as `agent-decision` issues. [detected; review]
  - Before adding a rule, decision, duty or job, search `policies/rules.yaml`, `decisions/`, AUTHORITY and ROLES; amend the nearest text; a new decision names what it supersedes. [failed; review]
  - No force-push, no deleting remote branches, no direct push to a default branch. [blocked]
- 7. Keep secrets and client material where they belong.
  - No secrets in git; no client documents in tooling repositories. [failed; review]
  - No use of Ali's signed-in browser while he is away; owner settings go through the API (0040). [review]

## Team: publishing (stream-aligned)
Customer: public readers. Deliverables: content and simulators. Owner of the no-ai-slop skill.
- Public repositories: nothing private, no client names, no figures from client work.
<!-- settings:end -->
