---
name: verification-harness
description: Adversarial verification harness that stops bad code from passing. After code is written it pins acceptance criteria and critical paths, has an independent adversary try to BREAK the code with real tests, dry-runs every critical path, EXECUTES the tests/lint/typecheck/build, runs a bounded automatic repair loop that never weakens tests, and refuses to call anything done without fresh passing evidence. Use for ANY task that writes, fixes or refactors code (features, bug fixes, refactors, scripts, PRs) and whenever the user says verify, test it, prove it works, harden, no regressions, or ship it. Built so cheap and small models ship verified code. Works in any agent harness (Claude Code, Codex, Gemini CLI, Cursor, Copilot, Windsurf, Cline, Aider, OpenCode, Amp) or pasted into any model's system prompt.
license: MIT
metadata:
  version: "1.0.0"
  credits: "Independent test design follows AgentCoder (Huang et al., arXiv:2312.13010)"
---

# Verification Harness

A cheap model with evidence beats an expensive model with confidence.
The model does not get smarter. **The harness stops bad code from passing.**

(In the AgentCoder paper, GPT-3.5 inside a write → independent-test → execute → fix loop scored
79.9% on HumanEval, beating GPT-4 working alone at 67.6%.)

Follow the stages **in order** and **literally**. Every rule says WHY in one line — follow the
why when a case is not covered. This file is self-contained: no scripts, no installs. It uses
whatever shell/test tools your harness already has.

---

## The 6 laws (read first, never break)

1. **No evidence = not done.** Never say "done / fixed / works / passes" unless you ran the
   checks AFTER your last edit and can paste their real output. *Why: models claim success
   without running anything; only exit codes and output count.*
2. **Never bend the tests.** Never delete, skip, `xfail`, `.only`, comment out, loosen, or
   rewrite a test (or its expected value) to make it pass. Never special-case test inputs. Never
   mock the code under test. Never add `# type: ignore`, `# noqa`, `eslint-disable`,
   `@ts-ignore`, `// @ts-nocheck`, or an empty `catch`/`except: pass` to silence a check.
   *Why: it makes the check green while the bug ships.*
3. **Evidence must be fresh.** Any code edit after a run makes that run worthless — run again.
   *Why: old output proves nothing about the code you are shipping.*
4. **Independent tests.** The tests that attack the code are designed from the SPEC, not from
   the implementation. *Why: tests written by the same mind that wrote the code share its blind
   spots (AgentCoder: independent tests 87.8% accurate vs 47.0% when written together).*
5. **Small, real changes.** Smallest diff that meets the spec; never leave `// ... existing
   code ...` placeholders; never call an API/function/package you have not confirmed exists.
   *Why: hallucinated APIs and deleted code are the top cheap-model bugs.*
6. **Stopping honestly is allowed.** Out of repair budget, or a test contradicts the spec →
   report **NOT VERIFIED** with reasons. *Why: an honest NOT VERIFIED is useful; a fake PASS is
   harmful.*

Keep a running **LEDGER** (template at the end) in your working notes or in
`.verification/LEDGER.md` if you can write files. Update it at every stage.

---

## Stage 0 — Spec first (before touching code; ~2 minutes)

1. Write the **task** in one line.
2. Write **acceptance criteria** as observable behavior — input → output / error / side effect —
   including what must NOT change. Number them `AC1, AC2, …`.
   Example: `AC1: empty cart → total 0` · `AC2: negative qty → raises ValueError` ·
   `AC3: existing discount codes behave exactly as before`.
3. List the **critical paths**, each linked to ACs. Minimum: one `happy` path AND one
   `error` or `boundary` path. Add `state` (writes, caches, mutations), `security` (untrusted
   input, auth, files, shell, SQL, paths) and `concurrency` paths whenever they apply.
   Every AC must be covered by at least one path.
4. **Find the real commands** for this project (see "Command finder" below): test, lint,
   typecheck, build. Write them in the ledger.
5. **Run the test command once NOW, before changing code.** Record which checks already fail.
   *Why: pre-existing failures must not be blamed on you — don't fix them unless asked.*

Trivial change (≤ ~20 lines, no logic branches)? You may use 1 path and 3 adversarial cases.
Auth, payments, data loss, security, concurrency? Double every minimum below.

## Stage 1 — Implement

1. Make the smallest change that satisfies the ACs. Leave unrelated code alone.
   *Why: broad rewrites create untested regressions.*
2. Before using any function, method, flag, or package: open the file, grep, or read the docs
   to confirm it exists with that exact signature. No new dependency without the user's OK.
3. Do NOT edit existing tests. You may ADD new test files.

## Stage 2 — Adversarial verification (try to BREAK it)

Someone who did NOT write the code must attack it. Use the most independent option you have:

| Option | How |
|---|---|
| **Subagent** (best) | Spawn a subagent/task. Give it ONLY: the task line, the ACs, the critical paths, the public interface (function signatures / endpoints / CLI), and the test command. NOT your reasoning, NOT the function bodies. |
| **Fresh session** | Start a new headless run with that same brief (e.g. `claude -p`, `codex exec`, `gemini -p`, `opencode run`, `aider --message`). |
| **Role-switch** (no subagents) | Write the line `ADVERSARY MODE: I have not seen the implementation.` Then work ONLY from the spec + interface. Do not scroll back to the code while designing tests. |

The adversary's job — output is **runnable tests, never opinions**:

1. Write tests into NEW test files (e.g. `test_adv_<feature>.*`). Never edit existing tests,
   never edit the code, never fix bugs.
2. Cover **every critical path**. Minimum **5 cases across ≥3 categories** from the catalog.
3. Include **at least one property/fuzz test**: many generated inputs checked against an
   invariant or a brute-force oracle (e.g. `sort(x)` is ordered and a permutation of `x`;
   `parse(format(v)) == v`; result equals a slow obviously-correct version).
   *Why: it catches special-casing and off-by-one bugs that example tests miss.*
4. Every expected value comes from the SPEC (cite the AC) — never from running the code.

**Attack catalog** (pick what applies):

- **basic:** the happy path from the spec, exactly.
- **boundary:** 0, 1, −1, max, max+1, first/last element, exactly-at-limit, off-by-one ranges.
- **input:** empty string/list/dict, `None`/`null`/`undefined`, whitespace-only, huge input,
  unicode/emoji, mixed case, leading zeros, NaN/Infinity, very long strings.
- **error:** invalid types, missing fields, malformed data, dependency failure (network/file/DB
  error), timeouts — assert the RIGHT error, not just "an error".
- **state:** repeated calls, idempotency, order of operations, stale cache, partial failure
  leaving half-written state, rollback.
- **concurrency:** two calls at once, race on shared state, double submit.
- **security:** injection (SQL/shell/path traversal `../`), unescaped HTML, auth bypass,
  secrets in logs, unbounded resource use.
- **api-misuse:** wrong call order, calling after close, extra/unknown params.
- **regression:** behavior the task must NOT change (AC for "unchanged").
- **language traps:** Python — mutable default args, integer division, `is` vs `==`, dict order,
  float equality. JS/TS — `==` coercion, `0`/`""` falsy, `NaN`, async not awaited, `this`
  binding, floating point, timezone/Date. Go — nil maps/pointers, loop var capture, error
  ignored. SQL — NULL semantics, empty IN list. Anywhere — timezones, locale, encoding,
  integer overflow, off-by-one in pagination.

Register every case in the ledger: `A1 | path | category | what it attacks | expected (ACn) | test id`.

## Stage 3 — Dry-run every critical path (trace, don't guess)

For EACH critical path, take **≥2 concrete inputs** (one normal, one edge) and walk the code
**as written, line by line** (not as you meant it). Fill one row per input:

| Input | Branches taken (line: condition → result) | Key state | Actual output | Expected (ACn) | Match? |
|---|---|---|---|---|---|
| `items=[]` | `L12: if not items → True` → return | total=0 | `0` | `0` (AC1) | ✅ |

Rules: trace loops at iteration 1, 2, last, and the exit · for external calls write the return
value you assumed · any ❌ → go to Stage 5.
*Why: tracing finds logic bugs without running anything, and it is the ONLY evidence when code
cannot be executed. It is a hypothesis — Stage 4 is the proof.*

## Stage 4 — Execute (real commands, real output)

1. Run: the full test suite + your new adversarial tests + lint + typecheck + build (whichever
   exist). Use a timeout; don't run watch mode.
2. Read the actual output. When you describe a failure, **quote the real error lines**. Never
   summarize output you did not see.
3. These count as **FAIL**: nonzero exit · "0 tests ran" / "no tests collected" · all tests
   skipped · timeout · a crash in collection · new warnings you introduced in strict projects.
   *Why: a filter that matches nothing exits 0 and looks green.*
4. Record each run in the ledger: command → exit code → pass/fail counts → key output lines.

### Command finder (use the project's own scripts first)

Look in this order: `package.json` scripts · `Makefile`/`justfile`/`Taskfile` · CI config
(`.github/workflows/*.yml`) · README/CONTRIBUTING · then these defaults:

| Stack (marker file) | Test | Lint / typecheck / build |
|---|---|---|
| Python (`pyproject.toml`, `setup.py`, `requirements.txt`) | `python -m pytest -q` (or `python -m unittest`) | `ruff check .` · `mypy .` / `pyright` · `python -m compileall -q .` |
| JS/TS (`package.json`; lockfile → npm/pnpm/yarn/bun) | `npm test` / `pnpm test` / `yarn test` / `bun test` (or `node --test`) | `npm run lint` · `npx tsc --noEmit` · `npm run build` |
| Go (`go.mod`) | `go test ./...` | `go vet ./...` · `go build ./...` |
| Rust (`Cargo.toml`) | `cargo test` | `cargo clippy -- -D warnings` · `cargo build` |
| Java/Kotlin (`pom.xml` / `build.gradle*`) | `mvn -q test` / `./gradlew test` | `mvn -q verify` / `./gradlew build` |
| .NET (`*.csproj`, `*.sln`) | `dotnet test` | `dotnet build` |
| Ruby (`Gemfile`) | `bundle exec rspec` / `bundle exec rake test` | `bundle exec rubocop` |
| PHP (`composer.json`) | `vendor/bin/phpunit` | `vendor/bin/phpstan analyse` |
| Swift (`Package.swift`) | `swift test` | `swift build` |
| C/C++ (`CMakeLists.txt`, `Makefile`) | `ctest --output-on-failure` / `make test` | `cmake --build build` / `make` |

No test framework at all? Write a minimal runnable test file with the standard library
(`unittest`, `node:test`, `go test`, etc.) — never skip execution because "there are no tests".

## Stage 5 — Automatic repair loop (max 5 iterations)

Run only if something failed (a check, a case, or a ❌ trace).

1. **Reproduce:** take the FIRST failure; read its full output.
2. **Root cause:** name the exact line and WHY it is wrong. Fix the cause, not the symptom.
   *Why: symptom fixes just move the bug.*
3. **Who is wrong?** Assume the CODE is wrong — unless the test contradicts a specific AC. Then
   quote that AC, fix the test to match it, and log it in the ledger as `TEST FIX: <reason + AC>`.
   Spec ambiguous? Escalate — don't guess.
4. **Minimal fix** to the code.
5. **Log:** `R<n> | failure | root cause (line + why) | fix`.
6. **Re-run EVERYTHING** (Stage 4), not just the failing test. *Why: fixes break other things;
   the full re-run is the regression guard.*
7. If code on a traced path changed → redo that path's trace (Stage 3).

**Stop conditions:**
- All green → Stage 6.
- Same failure after 2 attempts → full reset: re-read the spec and the failure from zero,
  discard your old theory (use a fresh subagent if you can). *Why: debugging in the same
  context decays fast after 2–3 attempts.*
- 5 iterations used, oscillation (fixing A breaks B, fixing B breaks A), or a test contradicts
  the spec → STOP, report **NOT VERIFIED** with the ledger.

**Forbidden "fixes"** (each one is cheating — never do them):

| Forbidden | Why |
|---|---|
| delete / skip / `xfail` / `.only` / comment out a test | hides the failure |
| change an assertion's expected value to match the output | the test now asserts the bug |
| `if input == <test value>: return <expected>` | special-casing; fails in production |
| mock or stub the function under test | the test no longer tests the code |
| `try/except: pass`, empty `catch`, `# type: ignore`, `eslint-disable`, `@ts-ignore` | silences the signal |
| run fewer tests / narrow the test command / disable a check | the gate must see everything |
| `// ... existing code ...` placeholders | deletes real code |

## Stage 6 — The gate (stop bad code from passing)

You may declare **PASS** only if ALL are true — check each box honestly:

- [ ] Every AC is covered by ≥1 critical path, and every path has ≥1 adversarial case.
- [ ] ≥5 adversarial cases across ≥3 categories, incl. ≥1 property/fuzz test (Stage 2 minimums).
- [ ] Every critical path has a dry-run trace with all rows ✅, redone after the last change.
- [ ] Test suite + adversarial tests + lint/typecheck/build ran AFTER the last edit, exit 0,
      and ran >0 tests (no "0 tests", no all-skipped).
- [ ] No test was deleted, skipped, weakened, or had its expected value changed (except a
      logged `TEST FIX` backed by a quoted AC).
- [ ] No new suppressions, special-cases, mocks of the code under test, or placeholders.
- [ ] Every repair iteration has a root cause logged; budget not exceeded.

Any box unchecked → **NOT VERIFIED**. Either loop back to Stage 5 or report it plainly. Never
soften it into "mostly works" or "should be fine".

**Final message format (always):**

```text
VERIFICATION: PASS | NOT VERIFIED
Checks (run after last edit):  <command> → exit <n> · <X passed / Y failed>   (one line each)
Adversarial cases: N across K categories (bugs found: B) · Traced paths: P · Repair iterations: R
Evidence: <paste the key output lines of the final passing runs>
Limits: <anything not executed, disabled, or environment-limited>
```

---

## Manual mode (the harness/model cannot run commands)

1. Do Stages 0–3 fully in writing: ACs, paths, adversarial tests as REAL test code, and a
   trace table for EVERY path (mandatory here — it is your only evidence).
2. Your verdict is always **`NOT VERIFIED — tests not executed`**. Give the user the exact
   commands to run.
3. When the user pastes real output produced AFTER your final edit, record it and re-apply the
   Stage 6 gate. PASS only when every check and case shows passing output.

## LEDGER template (copy and keep updated)

```markdown
# Verification ledger — <task, one line>
## Spec
- AC1: …            - AC2: …
## Critical paths
- P1 [happy] … (AC1)            - P2 [boundary/error] … (AC2)
## Commands
- test: …   - lint: …   - typecheck: …   - build: …
- baseline (before change): <which already failed>
## Adversarial cases
| id | path | category | attacks | expected (AC) | test id | result |
## Traces
| path | input | branches | state | actual | expected | ✅/❌ |
## Runs (latest after last edit)
| command | exit | passed/failed | key lines |
## Repair log
| R# | failure | root cause (line + why) | fix |
## Verdict: PASS | NOT VERIFIED — <reasons>
```

## Install anywhere (this one file is the whole skill)

- **Claude Code:** save as `~/.claude/skills/verification-harness/SKILL.md` (or
  `.claude/skills/verification-harness/SKILL.md` in a repo).
- **Codex CLI:** save as `~/.codex/skills/verification-harness/SKILL.md`, or paste the body
  into `AGENTS.md`.
- **Agent Skills–compatible harnesses** (Gemini CLI, OpenCode, Amp, Cursor, Copilot and
  others that read `SKILL.md`): put this folder in that harness's skills directory.
- **Cursor / Windsurf / Cline / Copilot / Aider (rules files):** paste everything below the
  frontmatter into `.cursor/rules/verification-harness.mdc`, `.windsurfrules`, `.clinerules`,
  `.github/copilot-instructions.md`, or `CONVENTIONS.md` (Aider: `--read CONVENTIONS.md`).
- **Any chat model / API:** paste everything below the frontmatter into the system prompt.

Then just ask for code as usual — or say "verify this" — and the harness runs.
