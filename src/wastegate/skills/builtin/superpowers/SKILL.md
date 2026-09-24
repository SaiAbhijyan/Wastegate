---
name: superpowers
description: Brainstorm, plan, then test-driven implementation and review.
provenance:
  upstream: obra/superpowers
  sha: unfetched
  license: unknown
  text: paraphrase
  scanned: n/a
quarantined: false
---
# Superpowers — plan, test first, then build

1. Clarify the goal in one or two sentences. If it is ambiguous, ask before building.
2. Write a short plan: steps, files, how each step is verified.
3. For each step: write a failing test, watch it fail, make it pass with the smallest change, re-run all tests.
4. Work on an isolated branch or worktree when the change is non-trivial.
5. Review your own diff before declaring done: does every change trace to the plan?
