# RESEARCH — sources, claims, evidence

Access date for all fetched rows: **2026-09-24**.
Evidence strength: **vendor** (the author's own page, no independent data) · **paper** (peer-reviewed or arXiv, read by us) · **our run** (measured in `results/`) · **unverified** (not fetched this session. Nothing here is summarized from memory).

Session-1 fetch budget (user decision): Jev docs, the Laya README and the Fable-Mode README only. Everything else is listed as "not fetched, unverified". No benchmark numbers are recalled from memory.

## Prior art

| item | status |
|---|---|
| "Strata" local scaffold (MISSION: heuristic/Laya/Jev backends, registry, router, composer) | **Not found** in this repo or container on 2026-09-24. Rebuilt from spec. Nothing reused. No quality inherited. |

## A. System One

### Jev (TypeSafe AI). Fetched: what-is-jev, jev/rlcd

| claim | source | strength | what we implement |
|---|---|---|---|
| Three primitives: choice (≤255 labelled options), score (ordered 2–10 levels), noul (P(yes) ∈ [0,1]) | what-is-jev | vendor | Same three types in `systemone/base.py`. We enforce choice ≤255 and score 2–10 in validation. |
| Several questions evaluated in parallel in one round trip | what-is-jev | vendor | `decide(state, questions)` takes a dict of questions and returns a dict of answers |
| Latency 70–500 ms, "40–200× faster than a frontier LLM" | what-is-jev | vendor | Nothing. We will measure our own latency when live calls exist. |
| Price $0.42 / M input tokens, output free | what-is-jev | vendor (price, not verified against a bill) | Catalog field `usd_per_mtok_in` stays empty until billed usage is seen |
| RLCD: "rewarded when its confidence matches how often it is actually correct" | jev/rlcd | vendor, **conceptual only** | Nothing. No loss, dataset, calibration numbers or independent study is published (confirmed absent on the page). We treat RLCD as a vendor method and implement our own calibration in Phase 3 with named rules: log score, Brier, RPS for ordinal. |
| API endpoint, request/response JSON, auth header | what-is-jev | **absent from page** | `systemone/jev.py` uses the Laya-documented Jev-compatible wire shape (see below) and is marked **unverified against Jev**. Base URL and auth header are unverified. Live calls are disabled. |

### Laya (NandhaKishorM/laya). Fetched: GitHub README

| claim | source | strength | what we implement |
|---|---|---|---|
| Apache-2.0; `pip install laya`; Python ≥3.10 | README | vendor | Optional backend. **Not installed in session 1** (user decision). |
| `Router().predict(state, questions, model=None, max_len=1024)`; question = `{type, instructions, criteria}`; choice criteria = `{label: description}`; score criteria = ordered list of level descriptions | README | vendor | `systemone/laya.py` builds exactly this dict. Parser handles `answers.<q>.{choice,score,noul,confidence}` and `usage`. |
| `laya-serve` exposes `POST /v1/systemone` in "Jev-compatible wire format"; `Authorization: Bearer` only if `LAYA_API_KEY` is set | README | vendor | The same request body is used for the Jev adapter (unverified against Jev itself) |
| Checkpoints: laya (ModernBERT-large 421M, EN, 512 ctx), laya-multilingual (mmBERT-base 322M), laya-typed-decisions (421M, 1024 ctx) | README | vendor | Config names only |
| Base checkpoints zero-shot 0.362 / 0.352 on the typed-decisions set vs a majority baseline of 0.461 (random 0.318) | README | vendor | **Design constraint:** Laya is never trusted zero-shot for routing. It needs fitting on our labels first. |
| Over-confident. Per-(type, option count) temperature on held-out data: mean ECE 0.466 → 0.081; multilingual has no fitted temperatures | README | vendor | Adapter carries a `temperature` slot. The fit happens in Phase 3 on our labels. The README's ECE is not our number. |
| ~20 options share `head_max_len`. At 77 options accuracy is 0.425 (vs their quoted Jev 0.870). Workaround `predict_shortlist()` | README | vendor | `systemone/shortlist.py` caps choice options at ≤20 before any backend call |
| `confidence` = 1 − normalised entropy (differs from Jev's formula) | README | vendor | Our `Answer.confidence` is documented per backend. Values are not comparable across backends until calibrated. |
| Score position bias (multilingual); the noul label pair can dominate on the EN checkpoint; negation failure example | README | vendor | Locked question templates. Noul label wording is frozen in `GATE_QUESTIONS`. |
| Fine-tuned 0.766 vs "Jev's published 0.727" on typed-decisions | README | vendor (Laya quoting Jev) | Not cited as a result. We did not find Jev's number at its source. |
| Noul `criteria` shape | README | **not shown** | Adapter sends a noul without criteria. Marked unverified. |

OpenJev / Laya-MLX / NanoJev: not fetched, unverified.

## B. Target behavior

| item | strength | notes |
|---|---|---|
| Fable-Mode (creativeskyai/Fable-Mode), fetched README | vendor | MIT. States it is not affiliated with Anthropic. `/ultra` = understand → design → implement → review. Roles: driver, finders, skeptics (majority vote), judge, builder/critic/scribe. Config: `subagent_model`, `subagent_effort`, `fleet`. Stated token budgets are hard caps. **No benchmark evidence**: "benchmarks keep showing…" has no citation. |
| GPT-6 Astra / Astra High, Terminal-Bench 4.0, DeepSWE, OSWorld | unverified | Not fetched. No numbers cited. |
| Claude Fable 5.1 (`claude-fable-5-1`), Amp ultra | unverified | Not fetched this session. Model ID taken from MISSION. It is listed in the catalog with `verified=false`. |

**Conflict:** MISSION lists the Fable-Mode phases as "understand → design → implement → adversarial review → exhaust". The README (primary source) lists `/ultra` as understand → design → implement → review, with skeptics in the review commands. "Exhaust" was not found. We follow the README.

### Behavior spec (what we copy vs what we never claim)
Copy (observable process):
1. Understand → design → implement → adversarial review.
2. Tests before code.
3. A skeptic role on a model tier ≤ the writer's tier. Its findings need support before they are surfaced.
4. The token budget is a hard cap.
5. Escalate only the unresolved slice to frontier.

Never claim: Astra OSWorld / Terminal-Bench results, Fable Vals Index, or "Ultracode quality". The default README phrase is "process inspired by Ultracode; quality unproven vs Fable 5.1".

## C. Router / CLI ecosystem. Not fetched, unverified

musistudio/claude-code-router, Brick (regolo), ypollak2/llm-router, AnyRouter CLI, Jev-Router, RCLI, LiteLLM, OpenRouter, Caveman Router, LangChain SmithTune: **not fetched, unverified.**

Decision (design-level; it does not depend on those sources' claims): the integration path is **proxy-first**. `wg proxy` will sit in front of Claude Code / Codex, rewrite `model` and inject the selected skills (Phase 2 / v1.1). A thin standalone `wg ask` comes later. The provider fabric (LiteLLM vs direct SDKs) is decided in Phase 2 after fetching LiteLLM docs.

## D. Skill upstreams. Not fetched, unverified

affaan-m/ECC, obra/superpowers, DietrichGebert/ponytail, multica-ai/andrej-karpathy-skills, leighstillard/feynman, evanshlee/feynman-technique, guicortei/feynman-technique, latent-spaces/brag, JuliusBrussee/caveman: **not fetched, unverified.** Their licenses and SHAs are unknown. The built-in skills in `src/wastegate/skills/builtin/` are **paraphrases written by us from the one-line job descriptions in MISSION**. They contain no copied text, and their frontmatter says so. creativeskyai/Fable-Mode: README fetched (MIT). The skill body is still our paraphrase.

## E. Papers. Not fetched, unverified (read before the phase that uses them)

| work | id given in MISSION | phase that needs it |
|---|---|---|
| Shazeer et al. 2017 MoE; Jiang et al. 2024 Mixtral | — | analogy only |
| FrugalGPT | arXiv:2305.05176 | Phase 2 cascade |
| RouteLLM | arXiv:2406.18665 | Phase 6 learned router |
| RouterBench | arXiv:2403.12031 | Phase 3 eval design |
| HybridLLM, ZOOTER, Routoo | — | Phase 6 |
| Gneiting & Raftery, proper scoring rules; Guo et al. 2017 temperature scaling | — | Phase 3 calibration |
| Reflexion, Self-Refine, Voyager, ExpeL, STaR / Quiet-STaR | — | Phases 4–5 |
| DSPy, GEPA, hermes-agent-self-evolution, SkillOpt, TextGrad, Promptbreeder, OPRO, APE | — | Phase 5 |
| MSCE | arXiv:2607.16621 | Phase 4. ID after our knowledge cutoff; existence unverified. |
| ELL / StuLife | arXiv:2508.19005 | Phase 4 |
| Self-Evolving Coding Agents survey | arXiv:2608.03392 | ID after our knowledge cutoff; unverified |
| InstructGPT, DPO, Lambert RLHF (arXiv:2504.12501), DPO-f+ (arXiv:2511.01043), PAHF (arXiv:2602.16173) | as given | Phase 4 / 6 |
| Taste-Bench | arXiv:2609.25804 | ID after our knowledge cutoff; unverified |

Nothing in this table is cited as evidence for any Wastegate behavior.
