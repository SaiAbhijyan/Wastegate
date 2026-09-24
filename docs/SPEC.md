# SPEC — Wastegate v1 contract

## Commands

| command | phase | session-1 status |
|---|---|---|
| `wg init` | 1 | writes `~/.wastegate/config.toml` (default: heuristic backend) if absent |
| `wg route "…"` | 1 | gate answers (value, distribution, confidence) + the routing decision. No LLM. |
| `wg prompt "…"` | 1 | prints the composed system prefix + user turn |
| `wg skills ls` / `show <id>` | 1 | built-in registry + provenance |
| `wg skills add owner/repo` / `rm` | 1.1 | not implemented (clone → pin SHA → scan → quarantine) |
| `wg models` | 1 | catalog by tier, with the `verified` flag |
| `wg eval run --suite route_quality` | 3 | session 1: dry-prints the frozen label file + sha256 only |
| `wg ask "…" --dry-run` / `--mock --replies DIR` / `--live` `[--repo P]` | 2a / 2b-prep | dry-run + mock implemented (no network); `--live` exits 2 without a key; no mode → exit 2. See docs/PHASE2.md, docs/PROVIDERS.md |
| `wg label new --out F [--pool P] --labeler NAME` | 3-prep | shows one unlabeled pool prompt at a time and appends the human's `kind` to JSONL; never shows a model prediction |
| `wg review -1\|+1` / `--verdict -1\|+1 [--note]` | 2a stub | writes verdict onto last log line only |
| `wg chat`, `run`, `feedback`, `evolve`, `report`, `proxy` | 2b–5 | stub, exit 2 |

`wastegate` and `wg` are the same entry point.

## Config
- User: `~/.wastegate/config.toml` (override with `WASTEGATE_HOME`). Project: `.wastegate/` (logs in `.wastegate/logs/`).
- Keys come **only from env**: `TYPESAFE_API_KEY` or `JEV_API_KEY` (Jev), plus provider keys in Phase 2. Keys are never written to config or logs.

```toml
[systemone]
backend = "heuristic"      # heuristic | laya | jev
[router]
frontier_threshold = 0.7   # P(needs_frontier) at or above this → frontier slice, if a frontier model exists
tests_threshold = 0.5
yagni_threshold = 0.5
ambiguous_threshold = 0.6
```

## System One schema (`systemone/base.py`)

```text
Question{id, type: choice|score|noul, instructions: str (locked template), options: tuple[str,...]}
  choice: 2..255 options (backends see ≤20 after shortlist)
  score:  2..10 ordered levels, low → high
  noul:   no options; answer value = P(yes)
Answer{value: str | float, distribution: dict[str, float] (sums to 1), confidence: float in [0,1], backend: str}
SystemOne.decide(state: str, questions: dict[id, Question]) -> dict[id, Answer]
```

For noul, `distribution = {"yes": p, "no": 1-p}` and `value = p`.

**Locked gate questions** (`GATE_QUESTIONS`; the wording is frozen, and changing it invalidates any calibration):

| id | type | options |
|---|---|---|
| kind | choice | ask, plan, implement, debug, review, research, ship, other |
| domain | choice | code, research, writing, data, ops, unknown |
| complexity | score | trivial, small, feature, deep, ultracode |
| needs_frontier | noul | |
| yagni | noul | |
| needs_tests | noul | |
| ambiguous | noul | |
| skill_primary | choice | 8 built-in ids + none |

Backend `confidence` definitions differ. Heuristic: max probability. Laya: 1 − normalised entropy. Jev: vendor-defined. They are **not comparable** until each backend is calibrated on our labels (Phase 3).

## Router output (`router.py`)

```text
Route{
  driver: Expert,            # role="driver"
  specialists: [Expert],     # skeptic | tester | researcher | bragger | frontier-slice
  skills: [skill_id],        # loaded bodies (caveman always included)
  clarify_first: bool,       # P(ambiguous) >= ambiguous_threshold
  reasons: [str]             # one per rule that fired
}
Expert{role, tier: local|cheap|mid|frontier, model: str|None, skills: [id], budget_tokens: int}
```

Rules (v1, deterministic):
- Driver tier: complexity trivial/small → cheap. feature/deep → mid. ultracode → mid driver + frontier-slice specialist.
- `frontier-slice` is added when P(needs_frontier) ≥ threshold **and** the catalog has a frontier model. The driver never becomes frontier by default.
- `skeptic` when complexity ≥ feature, on a tier ≤ the driver's (the cheapest available).
- `tester` when P(needs_tests) ≥ threshold. `researcher` when kind=research or domain=research. `bragger` when kind=ship.
- Skills: skill_primary (if not none) + kind→skill defaults + ponytail when P(yagni) ≥ threshold + caveman.
- A missing tier falls back to the nearest cheaper available tier, then the nearest dearer one. It works with only cheap+mid.

## Skill format
Agent Skills layout: `skills/<id>/SKILL.md` = YAML frontmatter + markdown body.

```yaml
---
name: karpathy
description: one line
provenance:
  upstream: multica-ai/andrej-karpathy-skills
  sha: unfetched            # pinned commit SHA once fetched
  license: unknown          # SPDX once verified
  text: paraphrase          # paraphrase | vendored
  scanned: n/a              # n/a for builtin paraphrase; scan result for imports
quarantined: false          # imports default true
---
```

Imported skills: scan with `skills/scan.py` → store findings → quarantined until `wg skills allow <id>` (Phase 1.1). A quarantined body is never composed.

## Composer
Prefix = role header + the bodies of the route's skills, in a fixed order, under a byte budget (default 12 KB; skills past the budget are dropped and reported). Unselected skill bodies never appear.

## Turn log (JSONL, `.wastegate/logs/turns.jsonl`)

```json
{"ts": "...", "turn_id": "...", "prompt": "...", "backend": "heuristic",
 "gate": {"kind": {"value": "debug", "distribution": {...}, "confidence": 0.61}, "...": {}},
 "route": {...}, "skills": [{"id": "karpathy", "sha": "<sha256 of SKILL.md>"}],
 "provider": null, "model_id": null, "tokens_in": null, "tokens_out": null, "usd": null,
 "calls": [{"role": "driver", "provider": "mock", "model_id": "mock-mid", "tokens_in": null, "tokens_out": null, "usd": null}],
 "latency_ms_gate": 3,
 "tool_trace": [], "tests": [], "review": null, "outcome": null}
```

`tokens_in`, `tokens_out`, `usd` stay `null` unless every call's provider response reported usage (and, for `usd`, a verified price exists). Redaction runs on the serialized line. It removes known key patterns (`sk-…`, `sk-ant-…`, `Bearer …`, `ghp_…`) and the literal values of the env keys above.

## Cost identity (measured in Phase 2+, never estimated)
`C = C_system_one + C_cheap + C_mid + p_escalate · C_frontier`. Every term comes from provider usage fields × a catalog price that has a verification date.

## Threat model

| threat | mitigation |
|---|---|
| Prompt injection via imported SKILL.md | static scan (injection phrases, tool-poisoning, exfil URLs, scripts/binaries, size cap); quarantine by default; provenance SHA; bodies never executed |
| Secrets in logs | env-only keys; regex + literal-value redaction on every log line; test with planted keys |
| Evolver editing evals / rollback | Phase 5: evolver write-allowlist = `skills/` only; eval-harness hash checked before and after; `evals/` and `results/` read-only to evolver |
| Label leakage / tuning to test | labels committed before backends; holdout run once; label changes named in commits |
| Vendor-number laundering | RESEARCH.md strength column; README limited to `results/` |
