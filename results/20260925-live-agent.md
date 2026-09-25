# 20260925 live smoke

**wiring + contract check, not a benchmark.** One `wg ask --live` invocation; not a quality claim.

- prompt: fix the off-by-one in sliding_windows
- tests: null
- test file changed: n/a
- tester parsed: n/a (not routed)
- skeptic parsed: n/a (not routed)
- follow-up ran: n/a
- mid escalation ran: n/a
- usd: null (no verified price in catalog)

## agent loop

**wiring check only, not a benchmark.**

- model: `openai/gpt-oss-20b` · harness: code-only · system prompt: 2108 B · max_steps: 8
- stop reason: provider error
- tool steps: none
- VERIFICATION: NOT VERIFIED (no tests run)
- checks: none

## provider error

HTTP 400 (redacted body, ≤1000 chars):

```text
{"error":{"message":"Tool choice is none, but model called a tool","type":"invalid_request_error","code":"tool_use_failed","failed_generation":"{\"name\": \"repo_browser.grep\", \"arguments\": {\"path\":\"tests/test_windows.py\",\"query\":\"sliding_windows\"}}"}}

```

redaction check: no configured key value present: yes
