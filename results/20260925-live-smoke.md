# 20260925 live smoke

**wiring check only, not a benchmark.** One `wg ask --live` invocation; not a quality claim.

- prompt: fix the bug in tiny_pkg and add a regression test
- tests: {"before": 1, "after": 0}
- usd: null (no verified price in catalog)

## driver: groq `openai/gpt-oss-120b` (tier mid)

host: api.groq.com

tokens_in=461 tokens_out=240 usd: null

raw usage JSON as returned:

```json
{
  "completion_time": 0.500628147,
  "completion_tokens": 240,
  "completion_tokens_details": {
    "reasoning_tokens": 136
  },
  "prompt_time": 0.020698221,
  "prompt_tokens": 461,
  "queue_time": 0.132010524,
  "total_time": 0.521326368,
  "total_tokens": 701
}
```

## tester: groq `openai/gpt-oss-120b` (tier mid)

host: api.groq.com

tokens_in=119 tokens_out=1914 usd: null

raw usage JSON as returned:

```json
{
  "completion_time": 3.989260024,
  "completion_tokens": 1914,
  "completion_tokens_details": {
    "reasoning_tokens": 860
  },
  "prompt_time": 0.006907544,
  "prompt_tokens": 119,
  "queue_time": 0.064666748,
  "total_time": 3.9961675679999997,
  "total_tokens": 2033
}
```

## skeptic: groq `openai/gpt-oss-20b` (tier cheap)

host: api.groq.com

tokens_in=116 tokens_out=4000 usd: null

raw usage JSON as returned:

```json
{
  "completion_time": 4.325089076,
  "completion_tokens": 4000,
  "completion_tokens_details": {
    "reasoning_tokens": 3853
  },
  "prompt_time": 0.00562123,
  "prompt_tokens": 116,
  "queue_time": 0.095338558,
  "total_time": 4.330710306,
  "total_tokens": 4116
}
```

redaction check: no configured key value present: yes

## Notes (written after the run; facts only)

- Provider: Groq only. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ALLOW_PAID` and the other free keys were unset for the run. No `--allow-paid`.
- Repo: a scratch copy of `tests/fixtures/tiny_pkg`, outside this repo. N=1. Heuristic gate: kind=debug, complexity=feature.
- **Try 1** (commit 9af94db): HTTP 403 before any edit. A keyless probe showed Cloudflare `error code: 1010` for Python-urllib's default User-Agent. Fixed in 58c5df7 by sending an explicit User-Agent.
- **Try 2** (this report, commit 58c5df7): the driver edited only `tiny_pkg/__init__.py` (`a - b` → `a + b`). Fixture tests went 1 → 0 (fail → pass).
- The driver did **not** add a regression test, although the prompt asked for one.
- The tester and skeptic replies were **invalid**: no `TESTER:` / `VERDICT:` line was found. The skeptic's `completion_tokens` = 4000 = its budget cap, 3853 of them reasoning tokens, so its reply was likely truncated. Both appear as unresolved. There is no frontier model, so nothing was escalated.
- Totals across the 3 calls: tokens_in 696, tokens_out 6154, as reported by Groq. usd: null. No price is verified, and Groq's free-tier billing was not checked.
- This shows the free-provider wiring works end to end once. It says nothing about model quality, cost, or reliability.
