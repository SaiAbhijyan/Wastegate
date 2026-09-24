# EVAL_PROTOCOL (pre-registration)

Filed 2026-09-24, before any score exists.

## Global rules
- Every run pins: git SHA, sha256 of the label file, skill SHAs, router config, System One backend + version, model IDs, effort settings, date.
- Split seed: **20260924**. It applies to any random split made later (e.g., the 100-task route set → 70 fit / 30 test).
- Baselines on every quality suite: **always-cheap**, **always-mid**, and **always-frontier** (only when a key exists; otherwise "BLOCKED", never estimated).
- Report: N, the per-item raw table, and a bootstrap 95% CI (10 000 resamples, seed above) once N ≥ 30. This harness is Phase 3 and is not run in session 1.
- Tokens and $ come from provider usage fields only.
- LLM-as-judge is never the only metric.
- Labels are frozen before the system under test runs. Any change after that is named in the commit message.
- Each result file contains a "what would falsify this" note.

## Suites

| # | suite | metric | success definition | session-1 status |
|---|---|---|---|---|
| 1 | route_quality | kind accuracy, escalate precision/recall, confusion matrix | human-labeled 100 tasks. Routed ≥ always-mid baseline on escalate F1 | labels v1 frozen (model-authored golden 15 + holdout 20). Human 100: **not started** |
| 2 | coding_small | tests passed, files touched, tokens, $ | routed pass-rate within X of always-mid while cost ≤ (1−Y)·mid. X and Y are fixed before the first run | **not started** (needs Phase 2) |
| 3 | yagni | LOC added, new deps, human "too much?" | routed ≤ always-mid on LOC/deps at equal pass-rate | not started |
| 4 | research | factual match, citation present, manual hallucination rate | citation on 100%, hallucination ≤ always-mid | not started |
| 5 | calibration | reliability diagram, ECE (15 equal-width bins), Brier, log score. RPS for ordinal complexity | ECE reported before and after temperature fit on the fit split, evaluated on the test split | **not run.** Forbidden on heuristic-vs-self-labels |
| 6 | evolution_safety | held-out delta, eval-harness hash unchanged | held-out metric does not drop. Hash is identical | not started (Phase 5) |

## Session-1 dev check (not a benchmark)
- Golden 15: a regression gate in `pytest`. The author saw these while writing the heuristic, so they measure nothing about generalization.
- Holdout 20: heuristic run **once**, raw hit/miss rows written to `results/20260924-dev-selflabel.md`. That file is labeled "self-labeled dev set, author=model, not a product benchmark". No CI, ECE or Brier. Misses stay unfixed in session 1.

## What we will NOT claim
- Any quality parity with Fable 5.1, GPT-6 Astra / Astra High, Opus, or "Ultracode".
- Any token or $ saving not measured from provider usage on suite 2+.
- Any calibration of any backend without suite 5 on our labels.
- Any Jev/Laya/Fable-Mode vendor number as our result.
- Heuristic gate accuracy as evidence of routing quality.

## Honest limits (mirrored in README)
- No quality comparison to Fable 5.1 or Astra exists.
- No token or $ savings have been measured. No provider calls are wired yet.
- The offline heuristic gate is a keyword scorer for CI. Its confidences are not calibrated.
- Laya and Jev adapters are request/response shapes only. Live calls are disabled. The Jev wire format is unverified against Jev.
- Built-in skills are our paraphrases of upstream packs. Upstream licenses and SHAs are not yet verified.
- The route labels so far were written by the model, not a human.
