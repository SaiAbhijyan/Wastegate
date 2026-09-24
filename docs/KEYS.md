# KEYS: which keys, when, and what they cost

Written 2026-09-24. Keys live in env vars only. They never go in config files, logs or commits (`log.redact` masks their values).

## Parked paid plan (not used yet)

- When we need frontier models: **$7.50 Anthropic API console + $7.50 OpenAI platform** credit. These are API accounts, not Claude Pro / ChatGPT Plus.
- Use them only for **escalation and verification**, and only after a **free live smoke works**.
- The $20 chat plans are for Claude Code Desktop, not for Wastegate.
- Paid keys are ignored even if set, unless you pass `wg ask --live --allow-paid` or set `ALLOW_PAID=1`.

| provider | env var | wired | billing class |
|---|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | yes, dark | paid |
| OpenAI | `OPENAI_API_KEY` | yes, dark | paid |

## Free keys to collect (the user creates these; we only document and wire)

| # | provider | get a key | OpenAI-compatible base | env var | Wastegate status |
|---|---|---|---|---|---|
| 1 | Groq | https://console.groq.com/keys | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | wired (dark) |
| 2 | Google AI Studio (Gemini) | https://aistudio.google.com/app/apikey | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` (preferred) or `GOOGLE_API_KEY` | wired (dark) |
| 3 | OpenRouter `:free` | https://openrouter.ai/keys | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | wired (dark). Only model IDs ending in `:free` are used unless paid is allowed |
| 4 | GitHub Models (optional) | GitHub token | not recorded | `GITHUB_TOKEN` | **not wired**. Value is redacted from logs |
| 5 | Cerebras (optional) | not recorded | not recorded | not chosen | **not wired** |
| 6 | Ollama, local (optional) | none | `http://127.0.0.1:11434/v1` | none | **not wired** |

Rows 4–6 are listed for later. Their URLs and base URLs were not checked this session.

## What "free" means here (read before trusting it)

- "Free" means the provider **offers a free tier** or `:free` model variants. It is **not a guarantee of $0**. A key created in a project with billing enabled (e.g. Google Cloud) can be charged. Check the provider console before running.
- Free tiers have rate limits and can change or disappear. Model IDs come and go. `models.toml` records where and when each ID was seen, and every row stays `verified=false` until a live call succeeds.
- OpenRouter `:free` variants may log or train on prompts, depending on the upstream provider's policy (unverified). Do not send secrets or private code you can't share.
- **OmniRoute / awesome-freellm-apis are directories or gateways, not a token balance.** Wastegate does not depend on them, and we do not rely on any "1.5B free tokens" style claim.

## Order of operations

1. Create one free key (Groq is the simplest). Export it in your shell, never in a file in the repo.
2. `wg ask --live --repo <scratch copy of tests/fixtures/tiny_pkg> "fix the bug in tiny_pkg and add a regression test"`
3. Check `results/YYYYMMDD-live-smoke.md`: the raw usage JSON is exactly what the provider returned, and `usd` is null.
4. Only after that works: consider the parked paid plan, for escalation and verification only.
