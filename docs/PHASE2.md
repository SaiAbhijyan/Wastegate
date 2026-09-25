# PHASE 2: generation contract

Status 2026-09-25: 2a (mock + dry-run) and 2b (live adapters) are implemented. Two Groq live checks were run, N=1 each:
- `results/20260925-live-smoke.md`: the fix passed, but the tester and skeptic replies were unparseable.
- `results/20260925-live-smoke-2.md`: the fix passed and both contracts parsed. No test file was added.

Verified field names: docs/PROVIDERS.md.

## Provider fabric (one interface)

```text
Provider.complete(model_id, system, messages, max_tokens) -> Completion
Completion{text, provider, model_id, usage: Usage | None, raw: dict | None}
Usage{input_tokens: int, output_tokens: int}
```

Adapters planned for 2b (not written): `anthropic` (Messages API), `openai`, `openrouter` (OpenAI-compatible wire). They sit behind the same interface, and the router only ever sees `Completion`. `mock` exists now and reads scripted replies from disk.

## Usage: from provider JSON only, never estimated

| provider | fields read | status |
|---|---|---|
| Anthropic Messages | `usage.input_tokens`, `usage.output_tokens` | to verify against provider docs before 2b |
| OpenAI Chat Completions / OpenRouter | `usage.prompt_tokens`, `usage.completion_tokens` | to verify |
| OpenAI Responses | `usage.input_tokens`, `usage.output_tokens` | to verify |
| mock | none | `usage=None` |

If the fields are missing, the token count is `null`. We never count words or use a local tokenizer as a substitute.

**USD:** `usage × price`, and only when that catalog entry has `verified=true` and a price date. Otherwise `usd=null`. `models.toml` carries **no prices** today.

## `wg ask` pipeline

gate → route → compose → **driver** → apply FILE blocks (path-guarded to the repo) → run repo tests (before/after exit codes) → **tester** (if routed; `TESTER: pass|fail` + `- finding` lines; failures join the unresolved list; a missing mock `tester.md` = skipped + reason) → **skeptic** (routed tier, cheaper than the driver when the route allows) → `escalate_slice(unresolved)` → JSONL log.

- `--dry-run`: stops after compose. Generation is empty and no provider is called.
- `--mock --replies DIR`: `MockProvider` returns `DIR/<role>.md`. Model IDs are `mock-cheap | mock-mid`, never real IDs.
- `--live`: real adapters on the key-filtered catalog (docs/PROVIDERS.md). Paid keys and models (Anthropic, OpenAI, non-`:free` OpenRouter) are ignored unless you pass `--allow-paid` or set `ALLOW_PAID=1`. Free-tier options: Groq, Gemini, OpenRouter `:free` (docs/KEYS.md). Exit 2 with `LiveDisabled` if no key is set (checked before any write). A successful live run also writes `results/YYYYMMDD-live-smoke.md` (never overwritten), with each call's raw `usage` JSON exactly as returned, keys redacted, and `usd: null`. One invocation makes up to 3 provider calls (driver, tester, skeptic). First run: results/20260925-live-smoke.md.
- No mode: exit 2 (live not enabled).

Driver edit formats. The driver receives this format and a redacted, capped repo context (the file list plus small text files; dotfiles and key-like files are skipped). All blocks are resolved in memory, in order, before anything is written. REPLACE old text must occur exactly once.

```text
<<<REPLACE rel/path.py
exact old text
<<<WITH
new text
<<<END
```

Whole-file form:

```text
<<<FILE rel/path.py
…full file contents…
>>>
```

Paths must be relative and resolve inside `--repo`. Anything else aborts the turn with no writes.

Tester and skeptic output contracts (TESTER_SYSTEM / SKEPTIC_SYSTEM): the first line must be `TESTER: pass|fail` or `VERDICT: approve|reject`, followed only by `- finding` lines. The parser takes the first matching line anywhere in the reply and tolerates markdown decoration. Findings are only the `- ` lines after that line. If the line is missing, the tester counts as skipped and the skeptic as reject (fail closed), and `parse_error` notes whether max_tokens was hit and how many reasoning tokens were used. Reviewer max_tokens comes from `[router] reviewer_budget_tokens` (default 8192). On reject, the findings are the **unresolved slice**.

## Escalation slice (`escalate.py`, a pure function)

`escalate_slice(unresolved, route, catalog) -> (Slice | None, reason)`
- nothing unresolved → `None`, "nothing unresolved"
- the route has no `frontier-slice` specialist, or the catalog has no frontier model → `None`, "no frontier available: report unresolved to user"
- otherwise → `Slice(model_id, findings=unresolved only, files=only files named in them, budget_tokens)`

It needs no key. 2a never *executes* a slice. It only decides the slice and logs it.

## JSONL turn fields added

`provider`, `model_id` (driver), `tokens_in`, `tokens_out`, `usd`, and `calls: [{role, provider, model_id, tokens_in, tokens_out, usd}]`. The totals are non-null only when **every** call reported usage. In mock and dry-run modes they are all `null`. Also added: `tests: {before, after}` exit codes, `edits` (paths), `skeptic: {verdict, findings}`, `escalation: {slice | null, reason}`.

## `wg review` (still a stub)

`wg review -1 | +1` or `wg review --verdict -1 | +1` `[--note …]` writes `review={verdict, note, ts}` onto the last log line. It does nothing else: instincts are Phase 4.

## Phase 2 gate (unchanged from MISSION)

The fixture tests pass under routed cheap or mid, and tokens are logged. **2a meets the fixture half with mocks only**, so it says nothing about model quality. The "tokens logged" half needs 2b.

## Out of scope for 2a

Live HTTP, provider SDKs, prices, `wg proxy`, ANTHROPIC_BASE_URL, OmniRoute/Headroom, laya install, ECE.

## wg chat

A REPL. For each line: gate → route → compose (instincts injected) → driver, with the last 10 history messages. `--dry-run | --mock --replies DIR | --live [--local] [--allow-paid]`. Edits are applied only with `--repo`, using the same parser, guard, all-or-nothing rule and before/after tests as `ask`. Without `--repo` they are printed but not applied. `/route /skills /exit`. Output is redacted. One JSONL line per turn.

## Local (Ollama)

`--live --local` uses only `provider = "ollama"` rows at `http://127.0.0.1:11434/v1` with no key. It probes `/v1/models` first; if Ollama is down it exits 2 before any write. Local rows never appear in cloud `--live`, `route`, `prompt` or dry-run views.

## Instincts v0

`wg review -1 --note "…"` appends one redacted preference (at most 200 characters) to `.wastegate/instincts.jsonl`, tagged with the reviewed turn's gate kind. Each compose injects up to 3: same kind first, then newest first. There is no decay, clustering or evolution yet.
