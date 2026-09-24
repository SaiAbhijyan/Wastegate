# 2026-09-24 dev check: heuristic kind on holdout 20

**self-labeled dev set, author=model, not a product benchmark.**

- git HEAD at run: `8be83f6d9cfb447446629840ea829efcbd293e59`
- labels.md sha256: `cbac12d4ac5be00f1be4ff2261ac2f65e280f4a58d3e69a7de79497ea91947d4`
- heuristic.py sha256: `a310ac848250be6f51aec8c373f9dca2788f6cf8a7d9851932076bdf3229aaeb`
- backend: heuristic (keyword rules, uncalibrated). No LLM, Laya, or Jev involved.
- run count on this holdout: 1. Misses left unfixed this session.

| id | prompt | label | predicted | top prob | hit |
|---|---|---|---|---|---|
| H01 | the nightly job hangs after the upgrade, figure out why | debug | debug | 0.85 | Y |
| H02 | write a CSV export endpoint for invoices | implement | implement | 0.55 | Y |
| H03 | what's the difference between a process and a thread? | ask | ask | 0.72 | Y |
| H04 | look over my PR diff for anything risky | review | review | 0.81 | Y |
| H05 | outline the steps to split the monolith into services | plan | plan | 0.88 | Y |
| H06 | find recent work on speculative decoding and summarize it | research | research | 0.61 | Y |
| H07 | draft release notes for v0.3 | ship | ship | 0.72 | Y |
| H08 | segfault when parsing empty input | debug | debug | 0.49 | Y |
| H09 | add retry with backoff to the http client | implement | implement | 0.37 | Y |
| H10 | how does python's GIL work? | ask | ask | 0.37 | Y |
| H11 | audit the auth middleware for token leaks | review | debug | 0.37 | N |
| H12 | compare vector databases for our use case, with sources | research | research | 0.61 | Y |
| H13 | roadmap for the next two sprints | plan | plan | 0.49 | Y |
| H14 | write a tweet thread announcing the launch | ship | ship | 1.00 | Y |
| H15 | test_upload fails intermittently on CI | debug | debug | 0.88 | Y |
| H16 | convert this callback code to async/await | implement | implement | 0.37 | Y |
| H17 | order me a pizza | other | other | 0.19 | Y |
| H18 | is this regex correct for emails? | review | review | 0.61 | Y |
| H19 | what's the literature on reward hacking in RLHF | research | research | 0.52 | Y |
| H20 | translate this paragraph into French | other | other | 0.19 | Y |

Hits: 19/20. N=20 and the labels were written by the model, so this is not evidence of routing quality.
## Skeptic note: this holdout is contaminated

- The author (model) wrote these 20 prompts into the session plan **before** writing `heuristic.py`,
  and then wrote the heuristic's cue lists. Several cues match holdout wording verbatim:
  `look over`, `risky`, `outline`, `roadmap`, `figure out why`, `intermittent`, `find (recent )?work`,
  `compare .+ with sources`, `announc`. Treat 19/20 as an upper bound, not a held-out estimate.
- "Top prob" is a softmax over rule hits. It is not a calibrated probability. For `other` (H17, H20)
  it is near-uniform (0.19): the prediction won only because no rule fired.
- The one miss (H11) shows the failure mode: `leaks` is a debug cue, and it tied the review cue `audit`.
  Tie-break goes to the earlier option in the kind list, so debug won. Not fixed this session.
- What would falsify "the heuristic routes kind well enough for CI": a human-labeled set written by
  someone who has not read `heuristic.py`. MISSION suite 1 (100 tasks) is that test. It has not been run.
