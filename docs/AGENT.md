# AGENT: tool loop + verification harness

Status 2026-09-25: implemented with **mocks only**. No live agent run yet.

The loop is the default for `wg ask --repo` / `wg run --repo` and `wg chat --repo`. `--oneshot` keeps the older single-reply path.

Action syntax: `<<<TOOL name\narg\n>>>` or a single line `TOOL name arg`, optionally inside markdown fences. `grep` takes an optional second line that scopes the search to a path.

## Loop
```text
prompt + --repo
 → System One gate (heuristic now; Jev later): the locked 8 questions + agent extras
 → AgentPlan{model_id, tools, max_steps, harness}
 → loop, at most max_steps (default 8):
     model reply = exactly ONE action → execute → "TOOL RESULT (<name>): …" appended → next step
 → verification gate → VERIFICATION: PASS | NOT VERIFIED
```
System One only routes. It never writes code.

Generation models for the loop come only from the live catalog. Eligible providers:
- `groq`
- `openrouter` (`:free` ids only, via the existing paid gate)
- `ollama` (`--local`)
- `mock`

With only `GROQ_API_KEY` set, only Groq ids are eligible.

## Gate questions
- The existing locked 8 are unchanged: kind, domain, complexity, needs_frontier, yagni, needs_tests, ambiguous, skill_primary.
- New locked templates (`systemone/agent_gate.py`):
  - `tool_loop` (noul): "Does this task need several tool calls (read, search, edit, run tests) rather than one answer?"
  - `model_pick` (choice): "Which available model should do this task?" The options are the live catalog ids, shortlisted to at most 20.
- Heuristic answers for the extras live in `agent_gate.py`. `heuristic.py` is frozen and untouched.

## Tools (all repo-scoped; every call printed and logged as `{step, tool, arg, ok}`)

| tool | action syntax | rules |
|---|---|---|
| read | `<<<TOOL read\npath\n>>>` | path must stay inside `--repo`; text only, capped at 8 KB |
| grep | `<<<TOOL grep\nregex\n>>>` | `rg` if installed, else a Python walk; at most 50 hits; skips `.git`, `.wastegate` |
| edit | `<<<REPLACE …<<<END` / `<<<FILE …>>>` | the existing parser + path guard; all edits resolve before anything is written |
| shell | `<<<TOOL shell\ngit diff\n>>>` | allowlist only (below); no shell interpreter; 120 s timeout |
| pytest | `<<<TOOL pytest\n>>>` | `python -m pytest -q` in `--repo` |

The shell allowlist:
- `git status …` and `git diff …`
- `pytest …` and `python -m pytest …`
- `python <file>.py` inside the repo

Everything else is denied: `rm`, `curl`, `python -c`, other `-m` modules, other git subcommands, and arguments that escape the repo.

To finish, the model replies `<<<DONE\nsummary\n>>>`. A reply with no action counts as the final answer.

Tools per task kind:
- implement / debug / other: all five
- ask / plan / review / research / ship: read, grep, shell

## How Jev attaches later
Jev uses the same `Question`/`Answer` interface. `jev.build_request` already shapes any question dict, the agent extras included. When `TYPESAFE_API_KEY` is set **and** the wire format has been verified against Jev's API guide, `JevSystemOne.decide()` goes live. `agent_gate` will then send `tool_loop` and `model_pick` to Jev instead of the heuristic rules; its routing contract does not change. Laya stays mocked until it is temperature-fitted on our labels.

## Verification gate (enforced in code, whatever the model claims)
1. Edits happened → a test run must come **after the last edit**; otherwise NOT VERIFIED.
2. PASS needs that run to exit 0 **and** report more than 0 passed. "No tests collected" or all-skipped is not a pass.
3. If the model says DONE without a post-edit test run and steps remain, it gets one nudge ("run pytest after your last edit").
4. Tampering means NOT VERIFIED even when tests pass:
   - on an existing test file: removed or changed `def test_` / `assert` lines; added `skip`, `xfail` or `.only`; a deleted test file;
   - in any file: added `# type: ignore`, `# noqa`, or `except…: pass`.
5. Repair cap 5: after 5 failing post-edit test cycles, the loop stops with NOT VERIFIED.
6. `max_steps` exhausted without meeting 1–2 → NOT VERIFIED.
7. When the harness is loaded, a baseline `pytest` runs before the loop and is recorded, so pre-existing failures are visible.
8. The verification-harness skill (user-supplied, MIT) is injected **only** when kind is implement/debug or the prompt matches verify / test it / prove / harden / ship.
9. The final lines are always `VERIFICATION: PASS | NOT VERIFIED` and `Checks: <cmd> → exit <n>`, plus `Reason:` when not verified.
10. No edits and no harness → `VERIFICATION: n/a (no edits)`.

## Honest limits
- It suits small repos. The model sees the file list and reads files through tools; there is no retrieval index.
- pytest only. Other test runners and linters are not wired as verification checks.
- It uses a text action protocol, not native function calling. A model that ignores the protocol just ends the loop.
- The shell allowlist is **not a sandbox**: `python file.py` can run arbitrary code in that file.
- The tamper detector is a line-level heuristic, not a semantic proof.
- When loaded, the harness skill adds ~16.6 KB (~4k tokens) to every step's system prompt.
- No parity claim with Claude Code, OpenCode, Fable 5.1 or Astra. No live agent run has been made yet.
