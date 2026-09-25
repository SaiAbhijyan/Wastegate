# PROVIDERS: verified wire fields

Access date: **2026-09-24**. "Verified" means the exact string was found in the source listed. It does not mean a live call was made. **No live call has been made.** Adapters are dark unless the key is set **and** `--live` is passed, and they are always dark under pytest.

## Anthropic Messages (`providers/anthropic.py`)
Source: https://platform.claude.com/docs/en/api/messages (docs.anthropic.com 301-redirects here). I grepped the raw `.md` of the page, because the WebFetch summary omitted the usage fields and guessed the auth header wrong.

| item | value | status |
|---|---|---|
| endpoint | `POST https://api.anthropic.com/v1/messages` | verified (curl example in page) |
| auth header | `X-Api-Key: $ANTHROPIC_API_KEY` | verified (curl example); we send lowercase `x-api-key` (HTTP headers are case-insensitive) |
| version header | `anthropic-version: 2023-06-01` | verified (curl example) |
| request body | `model`, `max_tokens`, `messages` (required); `system` (optional) | verified |
| response text | `content: array of ContentBlock`; we join `text` of blocks with `type == "text"` | verified field names |
| usage | `usage.input_tokens`, `usage.output_tokens`, `usage.cache_creation_input_tokens` (nullable), `usage.cache_read_input_tokens` (nullable) | verified |
| total input | "Total input tokens in a request is the summation of `input_tokens`, `cache_creation_input_tokens`, and `cache_read_input_tokens`." | verified (quoted). `tokens_in` = that sum |

## OpenAI Chat Completions (`providers/openai.py`)
The source platform.openai.com/docs/api-reference returned **HTTP 403** to WebFetch. Fallback source: OpenAI's own spec, https://raw.githubusercontent.com/openai/openai-openapi/main/openapi.yaml (github.com/openai/openai-openapi).

| item | value | status |
|---|---|---|
| base URL | `servers: - url: https://api.openai.com/v1`; path `/chat/completions` | verified (spec) |
| auth | `securitySchemes.ApiKeyAuth: type: http, scheme: bearer` → `Authorization: Bearer $OPENAI_API_KEY` | verified (spec) |
| response text | `choices[].message` → `ChatCompletionResponseMessage.content` | verified (spec) |
| usage | `CreateChatCompletionResponse.usage` → `CompletionUsage{prompt_tokens, completion_tokens, total_tokens, completion_tokens_details, …}` | verified (spec) |
| max tokens | request has both `max_completion_tokens` and `max_tokens`; we send `max_completion_tokens` | field names verified; which one is preferred per model is **unverified** |
| Responses API usage (`input_tokens`/`output_tokens`) | not used; `ResponseUsage` schema exists in the spec, fields not checked | unverified |

## OpenRouter (`providers/openrouter.py`)
Source: https://openrouter.ai/docs/api-reference/overview

| item | value | status |
|---|---|---|
| endpoint | `https://openrouter.ai/api/v1/chat/completions` | verified |
| auth | `Authorization: Bearer <OPENROUTER_API_KEY>` | verified |
| usage | `usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens` (required); `usage.cost` (optional) | verified |
| token counting | "Token counts are calculated using the model's native tokenizer." | verified (quoted) |
| request `max_tokens` | sent as `max_tokens` | **unverified** |
| `usage.cost` | kept in `Completion.raw` only; **not** used as `usd` | policy |

## Rules enforced in code
- Usage comes from the JSON above only. If a required field is missing, `usage=None` and the log shows `tokens_in/out = null`. We never count words or run a local tokenizer.
- `usd` stays `null` unless the catalog row is `verified=true` and has a dated price copied from a fetched pricing page. No prices are in `models.toml`, and no pricing page was fetched.
- Env keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`. They are read at call time. They are never logged (`log.redact` masks their values) and never repr'd.
- `ANTHROPIC_BASE_URL` is not read. The endpoints are fixed constants above. OmniRoute and Headroom are not wired.
- **Catalog rows** (all `verified=false`, no prices):
  - openai `gpt-5.4-mini` (cheap), `gpt-5.6-terra` (mid), `gpt-6-astra` (frontier). The IDs are in the `ModelIdsShared` enum of openai-openapi `openapi.yaml`, fetched 2026-09-24. Tier placement is our judgment; the mid and frontier placements follow MISSION.
  - openrouter `openai/gpt-4o` (cheap), `openai/gpt-5.2` (mid). These IDs were seen only in request examples on the OpenRouter overview page (2026-09-24). Their current availability is unverified. Tier placement is our judgment.
- **Provider selection under `--live`**: `live_catalog()` keeps only the rows whose provider key is set. With only `OPENAI_API_KEY` set, every routed call goes to OpenAI rows; it never silently falls back to Anthropic. No keys at all → `LiveDisabled`, exit 2, before any write. With several keys, the first row per tier in `models.toml` order wins (Anthropic first).

## Free-tier providers (added 2026-09-24): same `OpenAICompatible` client, different base URL and key

| provider | endpoint | key env | request max-tokens field | usage fields | status |
|---|---|---|---|---|---|
| Groq | `https://api.groq.com/openai/v1/chat/completions` | `GROQ_API_KEY` | `max_completion_tokens` | `usage.prompt_tokens`, `usage.completion_tokens` | base URL + env verified (console.groq.com/docs/openai); path, usage, max field verified (console.groq.com/docs/api-reference) |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` | `GEMINI_API_KEY`, else `GOOGLE_API_KEY` | `max_tokens` | parsed as OpenAI `prompt_tokens`/`completion_tokens` | base, path, `Authorization: Bearer $GEMINI_API_KEY` verified (ai.google.dev/gemini-api/docs/openai). **Unverified:** usage field names, max-tokens field, and `GOOGLE_API_KEY` (accepted at user request; not on that page) |
| OpenRouter `:free` | same as OpenRouter above | `OPENROUTER_API_KEY` | `max_tokens` (unverified) | as OpenRouter above | `:free` IDs taken from raw `openrouter.ai/api/v1/models` JSON (pricing prompt/completion `"0"`), each model page fetched (HTTP 200, exact ID in raw HTML) |

If a provider omits usage, `usage=None` and the log shows `tokens_in/out = null`. It is never estimated.

**Conflict recorded:** a WebFetch of `openrouter.ai/api/v1/models` returned a truncated, garbled summary. It claimed there were no `:free` IDs and listed ID prefixes that are not in the JSON. The raw JSON from the same URL (460 models, 20 `:free`) is the source of truth.

### Paid gate (`providers/live.py`)
- Paid means provider `anthropic` or `openai`, or an `openrouter` ID that does not end in `:free`. Groq and Gemini are free-tier providers. That does **not** guarantee $0 (docs/KEYS.md).
- `--live` keeps only rows whose key is set, then drops paid rows unless `--allow-paid` is passed or `ALLOW_PAID=1` (exactly `1`). One switch covers both.
- No keys → `no key or --live not set`. Only paid keys → `only paid keys/models available; set ALLOW_PAID=1 or pass --allow-paid`. Both exit 2 before any write.
- Several keys: the first row per tier in `models.toml` order wins.

### Free model rows (all `verified=false`; tier placement is our judgment; coding ability is not verified by us)
| provider | tier | id | seen on |
|---|---|---|---|
| groq | cheap | `openai/gpt-oss-20b` | console.groq.com/docs/models (Production) |
| groq | mid | `openai/gpt-oss-120b` | console.groq.com/docs/models (Production) |
| gemini | cheap | `gemini-3.5-flash-lite` | ai.google.dev/gemini-api/docs/models (Stable) |
| gemini | mid | `gemini-3.8-flash` | ai.google.dev/gemini-api/docs/models (Stable), docs/openai examples |
| openrouter | cheap | `cohere/north-mini-code:free` | raw openrouter.ai/api/v1/models JSON + model page |
| openrouter | mid | `qwen/qwen3.8-27b:free` | raw openrouter.ai/api/v1/models JSON + model page |

## Local Ollama (added 2026-09-25)
| item | value | status |
|---|---|---|
| endpoint | `http://127.0.0.1:11434/v1/chat/completions` | verified (docs.ollama.com/api/openai-compatibility: base `http://localhost:11434/v1/`) |
| key | none; a placeholder `Bearer ollama` is sent | verified: docs say "required but ignored" |
| usage (non-streaming) | parsed as OpenAI `prompt_tokens`/`completion_tokens` if present, else null | **unverified** |
| model | `qwen2.5-coder:7b` (tier local) | tag seen on ollama.com/library/qwen2.5-coder, 2026-09-25; `ollama pull` it yourself |

## HTTP User-Agent
All provider HTTP sends `User-Agent: wastegate/<version>`. On 2026-09-25, api.groq.com (behind Cloudflare) returned 403 `error code: 1010` for Python-urllib's default User-Agent (results/20260925-live-smoke.md, try 1).

## Groq usage fields as actually returned (2026-09-25, one run)
`prompt_tokens`, `completion_tokens`, `total_tokens`, `completion_tokens_details.reasoning_tokens`, `prompt_time`, `completion_time`, `queue_time`, `total_time`. `tokens_out` includes reasoning tokens as billed by Groq's count.
