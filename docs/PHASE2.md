# PHASE 2: generation contract

Status 2026-09-24: **2a (mock + dry-run) implemented. 2b (live providers) not started.** No live HTTP exists.

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

gate → route → compose → **driver** → apply FILE blocks (path-guarded to the repo) → run repo tests (before/after exit codes) → **skeptic** (routed tier, cheaper than the driver when the route allows) → `escalate_slice(unresolved)` → JSONL log.

- `--dry-run`: stops after compose. Generation is empty and no provider is called.
- `--mock --replies DIR`: `MockProvider` returns `DIR/<role>.md`. Model IDs are `mock-local | mock-cheap | mock-mid`, never real IDs.
- No mode: exit 2 ("live generation not implemented (Phase 2b)").

Driver edit format (a deliberately minimal whole-file replace; unified diffs are deferred):

```text
<<<FILE rel/path.py
…full file contents…
>>>
```

Paths must be relative and resolve inside `--repo`. Anything else aborts the turn with no writes.

Skeptic reply format: a first line `VERDICT: approve|reject`, then `- finding` lines. On reject, the findings are the **unresolved slice**.

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
