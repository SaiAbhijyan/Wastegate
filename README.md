# Wastegate

Cheap until it isn't. A System-One gated coding CLI: cheap models first, Fable/Astra only when the gate opens. Skills, MoE-style routing (role × skill × model tier), measured token spend.

```bash
wg route "fix the deadlock"
```

Status: Phase 1 (routing, skills, prompt composition, logging). No generation yet. See docs/MISSION.md.

## Honest limits

- No quality comparison to Fable 5.1 or Astra exists.
- No token or $ savings have been measured. No provider calls are wired yet.
- The offline heuristic gate is a keyword scorer for CI. Its confidences are not calibrated.
- Laya and Jev adapters are request/response shapes only. Live calls are disabled.
- Full list: docs/EVAL_PROTOCOL.md.
