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
- The catalog today has only `provider = "anthropic"` rows, so `--live` can reach only the Anthropic adapter until OpenAI or OpenRouter rows with verified IDs are added.
