# route_quality — frozen labels (v1)

Frozen: 2026-09-24. Author: model (Claude), golden list proposed by the user.
These labels are committed **before** any gate backend (`heuristic.py`) exists.
Any later label change must be named in the commit message that makes it.

Status: **self-labeled dev set, author=model, not a product benchmark.** A human-labeled set of
100 tasks (MISSION suite 1) is still to do.

## Rubric: `kind`

Pick the single label for the **primary deliverable** the user wants back.

| kind | deliverable | cue test |
|---|---|---|
| ask | an explanation; no code change, no defect being chased | "explain / what is / how does X work" about a concept or artifact |
| plan | a design, plan, roadmap, or migration steps; no code yet | "design / plan / outline / roadmap" |
| implement | a code or content change to a codebase (new feature, refactor, rename, simplify, convert) | the answer is a diff |
| debug | root cause of an observed defect (bug, hang, crash, race, flaky test, contention), usually plus a fix | a symptom is reported |
| review | an assessment of existing code/diff/artifact for risk or correctness; no change asked | "review / audit / is this correct / is this reachable" |
| research | a sourced synthesis of external literature or options | "survey / find papers / compare X with sources / literature" |
| ship | launch or communication material about the project | release notes, brag copy, tweets, launch video plans |
| other | anything outside software/research work | errands, translation, chit-chat |

Tie-breaks:
1. A reported symptom beats "why/what" wording → debug (e.g. "why is this mutex contended?").
2. A request to change code beats quality wording → implement (e.g. "simplify this module").
3. Security reachability questions about existing code → review.

## Golden 15 (regression gate; seen by author while writing the heuristic)

The user proposed this list. The model changed two labels **before freezing, and before any
heuristic code existed**:
- G04: user proposed `review`; frozen as `implement` (tie-break 2).
- G15: user proposed `ask`; frozen as `debug` (tie-break 1).

| id | prompt | kind | note |
|---|---|---|---|
| G01 | fix the race in worker.py | debug | |
| G02 | add session auth to the flask app with tests | implement | needs_tests |
| G03 | explain how git rebase differs from merge | ask | |
| G04 | simplify this 400-line utils module | implement | user proposed review |
| G05 | deadlock under load, find the invariant | debug | deep |
| G06 | write a design for multi-tenant billing | plan | |
| G07 | let's brag about this CLI | ship | |
| G08 | what does this traceback mean? | ask | |
| G09 | refactor to a plugin framework | implement | high yagni |
| G10 | survey papers on LLM routers | research | |
| G11 | rename foo to bar in one file | implement | trivial |
| G12 | is this SQL injection reachable? | review | |
| G13 | plan the migration off postgres | plan | |
| G14 | add a launch video shot list | ship | |
| G15 | why is this mutex contended? | debug | user proposed ask |

## Holdout 20 (run once at end of session 1; misses are reported, not fixed in that session)

| id | prompt | kind | note |
|---|---|---|---|
| H01 | the nightly job hangs after the upgrade, figure out why | debug | |
| H02 | write a CSV export endpoint for invoices | implement | |
| H03 | what's the difference between a process and a thread? | ask | |
| H04 | look over my PR diff for anything risky | review | |
| H05 | outline the steps to split the monolith into services | plan | |
| H06 | find recent work on speculative decoding and summarize it | research | |
| H07 | draft release notes for v0.3 | ship | |
| H08 | segfault when parsing empty input | debug | |
| H09 | add retry with backoff to the http client | implement | |
| H10 | how does python's GIL work? | ask | |
| H11 | audit the auth middleware for token leaks | review | |
| H12 | compare vector databases for our use case, with sources | research | |
| H13 | roadmap for the next two sprints | plan | |
| H14 | write a tweet thread announcing the launch | ship | |
| H15 | test_upload fails intermittently on CI | debug | |
| H16 | convert this callback code to async/await | implement | |
| H17 | order me a pizza | other | |
| H18 | is this regex correct for emails? | review | |
| H19 | what's the literature on reward hacking in RLHF | research | |
| H20 | translate this paragraph into French | other | |
