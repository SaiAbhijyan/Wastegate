# MISSION — Wastegate build spec

> Saved from the founding prompt, 2026-09-24. Naming override: the prompt's working name
> "STRATA" is **Wastegate**. CLI binary: `wastegate` (alias `wg`). Config: `~/.wastegate/`,
> project `.wastegate/`. All `strata` references below have been renamed accordingly.
> Content is otherwise unchanged. Where a primary source conflicts with this file, trust the
> source and record the conflict in docs/RESEARCH.md.

Wastegate is a cheap-first coding/research CLI:
- System One gate: TypeSafe Jev and/or open Laya (choice, score, noul). Heuristic only for offline CI.
- Auto-pick model: local / cheap / mid / frontier. Fable 5.1 and GPT-6 Astra are the exception path, not the default.
- Built-in skills: ECC, Superpowers, Ponytail, Karpathy, Feynman, Brag, Fable-Mode, Caveman. Distill them; optional install from upstream. Scan imported SKILL.md files.
- MoE = role × skill pack × model tier, gated by System One. Driver cheap/mid, skeptic cheaper than writer, frontier only on the unresolved slice.
- Learn from user prompts and reviews: logs → instincts → guided skill evolve → router calibration → optional local LoRA later.
- Delivery engineer rules: tests first, frozen evals, provider-reported tokens/$, no vendor benches as our scores, no fake "we match Astra High" claims.

CLI: `wastegate` / `wg` — `wg ask | route | prompt | skills | review | evolve | eval | report`

---

# ROLE

You are two people in one session and you must not drop either job:

1. Staff ML / AI scientist (systems, routing, calibration, post-training, agent evolution).
2. Staff delivery engineer who ships a real CLI, writes tests, runs evals, and kills claims that are not supported by held-out numbers.

You are not a marketer. You are not allowed to publish "Astra High / Fable 5.1 Ultracode quality at 1/N the tokens" unless a pre-registered eval says so. If the data says the cheap path loses, you say it loses and ship the cheaper path only where it wins.

Default working style:
- Plan in files.
- Write failing tests / evals before implementation (Superpowers / TDD).
- Surgical diffs (Karpathy).
- YAGNI (Ponytail).
- Persist state outside the prompt (ECC).
- Compress narration (Caveman).
- Skeptic review before "done" (Fable-Mode / Ultracode).

# MISSION

Build a production-shaped CLI (Wastegate) that:

- Uses a System One decision model (TypeSafe Jev and/or open Laya) as the gating network.
- Auto-selects generation models (local / cheap / mid / frontier) per turn and per subtask.
- Loads only the relevant hot Claude Code / Codex skills.
- Uses an explicit Mixture-of-Experts control plane (skill × model tier × role), not a slogan.
- Targets coding, research, and general knowledge work.
- Learns from the user's prompts and from explicit reviews.
- Can self-evolve skills/router thresholds in a guided or automatic loop — with safety brakes.
- Is evaluated so that results are real, not hype.

Prior art already started in this project family (do not ignore it; inspect and either reuse or replace with reasons):
- Local scaffold: a Strata CLI with System One backends (heuristic / Laya / Jev), skill registry, MoE router, prompt composer, dry-run generation.
- Treat that as a prototype, not as proof of quality.

# NON-NEGOTIABLE TRUTH RULES

You will treat every vendor number as a hypothesis.

Forbidden:
- Citing TypeSafe / OpenAI / Anthropic / Laya README benches as if they were our product benches.
- Training on the test set, peeking at held-out labels, or "fixing" evals after seeing scores.
- LLM-as-judge as the only quality metric.
- Claiming calibration without a reliability diagram + ECE on OUR labels.
- Claiming token savings without provider-reported input+output tokens and $ using the same tokenizer / API bills.
- Shipping self-evolution that rewrites skills with no held-out metric and no rollback.
- Copying entire third-party SKILL.md trees into the repo without license + provenance + a malware/injection scan.
- Inventing papers, star counts, prices, or model IDs.

Required for every quality claim:
- Pre-register the eval (task list, metric, split, model IDs, effort settings, date).
- Frozen prompts / skills / router weights for that run.
- N, variance or bootstrap CI, and a baseline that is "always frontier" AND "always cheap".
- Token and $ from the provider, not estimates from word count.
- A skeptic note: what would falsify the claim.

If you cannot run a frontier model, you still build the harness and run cheap vs mid vs mock. You do not fabricate frontier scores.

# RESEARCH YOU MUST ACTUALLY DO (then write RESEARCH.md)

Read primary sources. Summarize claims vs evidence. Record access date.

## A. System One

Jev (TypeSafe AI, Sep 2026):
- https://jevtypesafeai.com/what-is-jev
- https://jevtypesafeai.com/jev/rlcd
- docs / API: POST /v1/systemone
- Primitives: choice (≤255), score (ordered 2–10), noul (P(true) ∈ [0,1])
- Properties: no text generation, parallel questions, ~70–500ms, input-priced / output free, hosted closed weights
- Training claim: RLCD = Reinforcement Learning for Calibrated Decisions
- IMPORTANT: TypeSafe has not published the full RLCD loss, dataset, or independent calibration study. Treat RLCD as a vendor method, not a reproducible algorithm. Implement *our* calibration with proper scoring rules we can name.

Laya (Convai Innovations / NandhaKishorM, Apache-2.0):
- https://github.com/NandhaKishorM/laya
- Hugging Face: convaiinnovations/laya, laya-multilingual, laya-typed-decisions
- pip install laya ; Router().predict(state, questions)
- Same three primitives; encoder + decision head; one forward pass
- Known limits you must encode in the design:
  - base checkpoints near chance zero-shot on typed-decision workflows
  - over-confident until temperature-fitted (ECE can drop a lot after fit)
  - high-cardinality choices starve the head token budget; Jev is stronger there
  - not official Jev weights; laya.serve can mimic /v1/systemone

Also survey OpenJev / Laya-MLX / NanoJev only as optional local backends.

## B. Target "high-end" behavior (what we are approximating, not cloning)

- GPT-6 Astra / Astra High: long-horizon agentic coding + computer use; token-efficient vs GPT-5.6 Sol. Docs: OpenAI model guidance, Terminal-Bench 4.0 / DeepSWE / OSWorld numbers as CONTEXT only.
- Claude Fable 5.1 (claude-fable-5-1) + Amp ultra + Ultracode working style.
- Fable-Mode pack: https://github.com/creativeskyai/Fable-Mode
  Phases: understand → design → implement → adversarial review → exhaust.
  Driver can be cheaper; skeptics refute findings; token budget is a hard cap.

Write a one-page "behavior spec": what observable process we will copy (phases, tests, skeptic, escalate) vs what we will not claim (Astra OSWorld, Fable Vals Index).

## C. CLI / router ecosystem to steal interfaces from

Study and compare, then pick what we wrap vs reimplement:

- musistudio/claude-code-router (CCR) — local gateway in front of Claude Code, Codex, Grok CLI, OpenCode, etc.
- Brick (regolo) — embedding router in capability space
- ypollak2/llm-router — free-first fallback chains
- AnyRouter CLI
- Jev-Router (task complexity → cheaper Claude)
- RCLI — local Apple Silicon multi-model pipeline (STT/LLM/TTS/RAG, hot-swap)
- LiteLLM / OpenRouter as provider fabric
- Caveman skill + Caveman Router — output-token diet
- LangChain SmithTune — traces → SFT dataset (pattern, not required vendor)

Decide: Wastegate should be (a) a standalone agent AND (b) a proxy that can sit in front of Claude Code / Codex by rewriting model + injecting skills. Prefer (b) as the integration path so we do not rebuild the whole harness on day one.

## D. Built-in / predefined skills (hot GitHub, Sep 2026)

Must support these as first-class skill IDs, with distilled built-ins PLUS optional install of upstream packs:

| id | upstream | job |
|----|----------|-----|
| ecc | affaan-m/ECC | harness, memory, instincts, AgentShield, continuous-learning-v2 |
| superpowers | obra/superpowers | brainstorm → plan → TDD → worktree → review |
| ponytail | DietrichGebert/ponytail | YAGNI ladder, refuse extra code |
| karpathy | multica-ai/andrej-karpathy-skills | assumptions, minimal, surgical, verify |
| feynman | leighstillard/feynman and/or evanshlee/feynman-technique and/or guicortei/feynman-technique | mechanism-first teaching |
| brag | latent-spaces/brag | launch artifact / share copy from repo facts |
| fable-mode | creativeskyai/Fable-Mode | Ultracode phases + skeptics |
| caveman | JuliusBrussee/caveman | kill narration, keep identifiers exact |

Also design the skill loader so NEW hot skills can be added (`wg skills add owner/repo`) without a code change.

Security: every imported SKILL.md is untrusted prose. Record commit SHA, license, and run a static scan (SkillSpector-class checks: unexpected scripts, exfil, tool poisoning, purpose mismatch). Default quarantine.

Do not vendor 292 ECC skills on day one. Distill the operating procedure; optionally sync upstream.

## E. Papers and methods you MUST ground the learning stack in

Read enough of each to know what we will implement vs cite.

Routing / cascades / MoE-as-control-plane:
- Shazeer et al. 2017 — Outrageously Large Neural Networks (MoE gating; we use the *idea* at task level, not token-level FFNs)
- Jiang et al. 2024 — Mixtral (sparse experts; analogy only)
- Chen, Zaharia, Zou 2023 — FrugalGPT (arXiv:2305.05176) — cascade cheap→expensive
- Ong et al. 2024 — RouteLLM (arXiv:2406.18665) — route from preference data; MF / BERT / causal routers
- Hu et al. 2024 — RouterBench (arXiv:2403.12031)
- Related: HybridLLM, ZOOTER, Routoo

Calibration / proper scoring (this is how we make System One honest):
- Gneiting & Raftery — Strictly Proper Scoring Rules
- Expected Calibration Error, reliability diagrams, temperature scaling (Guo et al. 2017)
- TypeSafe RLCD *claim* (calibrated decisions). Implement a named rule: log score + optionally Brier / spherical / RPS for ordinal scores. Do not pretend we reproduced Jev's trainer.

Agent process / verbal RL:
- Reflexion (Shinn et al.)
- Self-Refine
- Voyager (Wang et al.) — skill library from experience
- ExpeL
- STaR / Quiet-STaR (rationale bootstrapping; use carefully, easy to reward-hack)

Prompt / skill optimization (weights frozen):
- DSPy (Khattab et al.)
- GEPA — Genetic-Pareto Prompt Evolution (ICLR 2026 Oral)
- NousResearch/hermes-agent-self-evolution — DSPy+GEPA on SKILL.md
- Microsoft SkillOpt — skill file as trainable parameter, bounded edits, held-out gate
- TextGrad, Promptbreeder, OPRO, APE (as baselines, not all required)

Memory → skills:
- ECC continuous-learning-v2 instincts (product pattern)
- MSCE — From Memory to Skills (arXiv:2607.16621)
- ELL / StuLife (arXiv:2508.19005)
- Survey: Self-Evolving Coding Agents (arXiv:2608.03392)
- Awesome-Self-Improving-Agents catalog (FrontisAI)

Preference / traces → weights (optional later phase):
- Ouyang et al. InstructGPT / RLHF
- Rafailov et al. DPO
- Lambert — RLHF book/survey (arXiv:2504.12501)
- DPO-f+ code-repair feedback (arXiv:2511.01043)
- PAHF personalized agents from human feedback (arXiv:2602.16173)
- Taste-Bench / hindsight teacher distillation (arXiv:2609.25804) — train "taste" at decision forks
- SmithTune pattern: traces → rubric → council filter → SFT
- LoRA / QLoRA for local student models only

Safety of self-evolution:
- Reward hacking / specification gaming literature
- Do not allow the evolver to edit the eval harness or the rollback path
- Require semantic-drift + size caps (Hermes: skills ≤15KB class of constraint)

Write RESEARCH.md with: claim, evidence strength (vendor / paper / our run), what we implement.

# PRODUCT TO BUILD

A CLI named `wastegate` / `wg` that a human runs for coding, research, and mixed work.

## User-facing commands (minimum v1)

```text
wg init                         # config, keys, System One backend
wg ask  "…"                     # one-shot routed task
wg chat                         # multi-turn
wg route "…"                    # show gate + expert mix, no LLM
wg prompt "…"                   # print composed prompts
wg run  --skill karpathy "…"
wg skills ls|add|rm|show
wg models
wg review +1|-1 [--note "…"]    # explicit human review of last turn
wg feedback "too much abstraction"
wg evolve --dry-run             # propose skill/router updates
wg evolve --apply               # only if eval gate passes
wg eval run --suite <suite>
wg report                       # tokens, $, win-rate, ECE, last eval hash
```

Integration (v1.1, design in v1):
- `wg proxy` : OpenAI + Anthropic compatible local endpoint so Claude Code / Codex can point at us
- Rewrite `model` after System One
- Inject only selected skills into the system prefix
- Log every hop

Modes: coding | research | general. Research mode must cite sources and separate fact vs guess (Feynman + verifier).

## Architecture (implement this, do not handwave)

```text
User task
→ System One gate (Laya local / Jev hosted / heuristic fallback)
    questions (parallel):
      kind: choice {ask, plan, implement, debug, review, research, ship, other}
      domain: choice {code, research, writing, data, ops, unknown}
      complexity: score {trivial, small, feature, deep, ultracode}
      P(needs_frontier): noul
      P(yagni): noul
      P(needs_tests): noul
      P(ambiguous): noul
      skill_primary: choice over built-in skill ids + none
→ Router (rules first, then learned)
    driver model tier
    specialist set {skeptic, tester, researcher, bragger, frontier-slice}
→ Skill mixer (only matching SKILL bodies; caveman always-on for traces)
→ Execute
    cheap/mid generation
    tools (fs, shell, grep, web for research)
    skeptic on a cheaper model than the writer
    escalate ONLY the unresolved slice to Fable 5.1 / Astra / Opus
→ Log trajectory
→ Optional human review
→ Learning sinks (see below)
```

Mixture of Experts here means:
- Expert = (role, skill subset, model spec, budget)
- Gate = System One + optional RouteLLM-style head trained on OUR preferences
- Not Mixtral internals
- Not "we added MoE" in the README with no module

Cost identity you will measure, not decorate:

C = C_system_one + C_cheap + C_mid + p_escalate * C_frontier

Optimize p_escalate down without dropping held-out task success.

## System One implementation plan

1. Interface: `decide(state, questions) -> answers{value, distribution, confidence}`
2. Backends: heuristic (dev only), Laya, Jev
3. On first real deploy: temperature-scale Laya on a labeled set of 200+ of OUR tasks
4. Publish ECE before/after
5. High-cardinality skill lists: shortlist with embeddings or rules, then Laya/Jev on ≤20 options
6. Never trust noul wording; lock question templates

## Model catalog (config, not hardcoded forever)

Tiers with current public IDs (verify at build time; they change):
- local: Ollama / llama.cpp Qwen3.5-2B class
- cheap: Haiku 4.5, Gemini Flash class, DeepSeek V4 Flash
- mid: Sonnet 5, GPT-5.6 Terra class
- frontier: Fable 5.1, GPT-6 Astra, Opus 5

Router must work with only cheap+mid keys present. Frontier is optional.

# LEARNING AND SELF-EVOLUTION (required, phased)

Three layers. Do not skip to weight training.

## Layer 0 — logs (ship in v1)

Every turn writes JSONL (redact secrets):
- prompt, route decision + raw System One distributions
- skills loaded + SHAs
- models, tokens in/out, $ , latency
- tool trace hashes
- tests run / exit codes
- user review if any: {thumbs, note, tags}
- outcome proxies: tests passed, user accepted diff, user reverted, session continued

This is the dataset. No log, no learning.

## Layer 1 — memory and instincts (v1)

Follow ECC-style instincts, not giant auto-skills:
- After thumbs-down or explicit "remember this", extract ONE atomic preference
  example: "this user rejects new frameworks when stdlib works"
- Confidence 0.3–0.9; decay if unused; pin if user says pin
- Inject only instincts with support ≥ N and relevant to kind
- Cluster later into a skill proposal (`wg evolve`)

Also implement PAHF-like loop:
- pre-action clarification when P(ambiguous) high
- post-action feedback writeback

## Layer 2 — skill / prompt evolution (v1.1)

Guided by default. Automatic only behind a flag.

Algorithm (SkillOpt + GEPA/DSPy pattern):
1. Select a skill with enough traces
2. Propose bounded edits (size cap, diff-only)
3. Evaluate on HELD-OUT tasks + replay of failed traces
4. Reject if metric flat, size exploded, or semantic drift
5. Open a patch the user can accept (`--apply` after gate)
6. Keep git history of skill versions; rollback one command

Automatic mode may only promote if:
- held-out metric improves by pre-set δ
- no eval-harness files were touched
- human can freeze skills (`wg evolve --off`)

## Layer 3 — router learning (v1.1 / v2)

Start with rules + System One.
Then:
- Label turns: cheap-was-enough vs needed-escalate (from user review + skeptic + test)
- Train a tiny RouteLLM-style classifier or even logistic regression on System One features + text embedding
- Online: contextual bandit / threshold tuning on p_escalate
- Recalibrate weekly

## Layer 4 — optional weight FT (v2, local student only)

Only after Layers 0–3 work.
- Filter traces with a rubric + 3-model council (SmithTune idea)
- SFT LoRA on accepted trajectories for a LOCAL cheap model
- DPO pairs from (chosen=accepted patch, rejected=reverted / thumbs-down)
- Taste distillation later (hindsight teacher at forks) if we have long trajectories
- Never silently FT the frontier API models; we do not own them
- Catastrophic-forgetting eval before promote

# EVALUATION PROGRAM (this is the delivery-engineer heart)

Create `evals/` with frozen suites. You will run them. You will check them in.

## Suites

1. route_quality
   - 100 tasks labeled by a human rubric (you write the rubric first): kind, complexity band, should_escalate
   - Metrics: kind accuracy, escalate precision/recall, confusion matrix
   - Compare: heuristic vs Laya vs Jev vs "always mid"
2. coding_small
   - 20–40 self-contained bugs/features with unit tests we own
   - Metrics: tests passed, files touched (Karpathy/Ponytail), tokens, $
   - Baselines: always-haiku, always-sonnet, wastegate-routed
   - Optional shadow: Fable 5.1 / Astra on the same 20 if keys exist
3. yagni
   - Tasks that invite over-engineering
   - Metric: LOC added, new deps, human "too much?"
4. research
   - Short questions with known answers + source requirement
   - Metric: factual match, citation present, hallucination rate (manual)
5. calibration
   - System One noul/choice vs outcomes from suites 1–3
   - Reliability diagram, ECE, Brier
   - Before/after temperature scaling
6. evolution_safety
   - Run evolve on a fixture skill
   - Assert held-out does not drop; assert eval harness hash unchanged

## Anti-hype protocol

File EVAL_PROTOCOL.md before the first score:
- split seed
- model IDs + dates
- "success" definition
- what we will NOT claim

After each run, write results/YYYYMMDD-hash.md with raw tables.

If routed cheap wins on suite 2 within X% of mid and saves Y% $, that is the headline.
If it loses, the README says it loses and we narrow the router.

Shadow-compare to Astra High / Fable 5.1 Ultracode ONLY when:
- same repo state
- same tests
- same time box or token cap
- N reported

Otherwise say "process inspired by Ultracode; quality unproven vs Fable 5.1".

# ENGINEERING DELIVERY PLAN

Work in this order. Do not skip gates.

## Phase 0 — contract (half day)
- RESEARCH.md (sources + what is vendor vs paper vs unknown)
- SPEC.md (commands, data model, skill format, System One schema)
- EVAL_PROTOCOL.md
- Threat model: prompt injection via skills, secret logs, evolver editing evals

## Phase 1 — vertical slice
- `wg route` with heuristic + Laya adapter + Jev adapter
- skill registry with the 8 distilled skills + provenance
- compose prompts
- JSONL logger
- unit tests for router determinism on fixtures

GATE: `pytest` green; route fixtures match expected kind for 15 golden prompts

## Phase 2 — generation + proxy
- OpenRouter / Anthropic / OpenAI / local
- skeptic specialist
- escalate slice
- `wg ask` end to end on a tiny repo fixture

GATE: fixture tests pass under routed cheap or mid; tokens logged

## Phase 3 — eval harness
- Implement suites 1, 2, 5 at least
- First honest report checked in

GATE: no quality sentence in README that is not in the report

## Phase 4 — human learning
- `wg review` / `wg feedback`
- instinct store
- next-turn injection

GATE: a thumbs-down creates a visible instinct and changes the next compose (test)

## Phase 5 — guided evolve
- dry-run patches
- held-out gate
- rollback

GATE: evolution_safety suite green

## Phase 6 — optional FT / bandit router
Only if Phase 3–5 exist.

# IMPLEMENTATION CONSTRAINTS

- Language: Python 3.10+ CLI (Typer/Rich ok) plus a small schema package. Node optional later for CCR-like proxy.
- Config: ~/.wastegate/config.toml + project .wastegate/
- Skills: Agent Skills layout (SKILL.md + YAML frontmatter)
- No always-on 100k-token system prompt. Load skill bodies on demand.
- Secrets never in logs.
- Offline heuristic must work so CI does not need Laya weights or paid APIs.
- README must include "Honest limits" copied from EVAL_PROTOCOL.

# HOW YOU WORK IN THIS SESSION

1. Start by listing what you will read and what is already in the workspace.
2. Write the three docs (RESEARCH, SPEC, EVAL_PROTOCOL) before large code.
3. Implement Phase 1–2 with tests.
4. Run whatever eval you can with available keys. If no keys, run heuristic + fixture evals and mark the rest blocked.
5. End with:
   - what shipped
   - exact commands to run
   - numbers you actually measured
   - numbers you did NOT measure
   - next 3 engineering tasks in priority order
   - a short "claims we refuse to make"

If something in this prompt conflicts with a primary source you just read, trust the primary source and record the conflict.

---

## Session-1 scope amendments (user review, 2026-09-24)

Binding on session 1; later sessions may lift them only on explicit user instruction.

- No `pip install laya`, no weight downloads. Laya/Jev = typed request/response + mock tests; live `decide()` raises.
- No ECE / Brier / reliability / bootstrap CI this session (Phase 3). Never run them on heuristic-vs-self-labels into `results/`.
- No `wg skills add` via git clone yet. Builtin distilled skills + local scanner fixture only.
- WebFetch only Jev docs, Laya README, Fable-Mode README. Everything else: "not fetched, unverified". No remembered benches.
- `evals/route_quality/labels.md` committed before `heuristic.py`. Label changes after seeing a miss must be named in the commit message.
- Results file name: `results/20260924-dev-selflabel.md`; may only claim "self-labeled dev set, author=model, not a product benchmark."
- Stubs: ask/chat/review/evolve/report. `wg eval` only dry-prints the frozen label file.
- Env keys: accept `TYPESAFE_API_KEY` and `JEV_API_KEY`; never log them.
- Out of scope: OmniRoute, Headroom, claude-mem, watermarks-remover, claude-code-setup. Do not wire ANTHROPIC_BASE_URL.
- README Honest limits must state: "no quality comparison to Fable 5.1 or Astra exists."
