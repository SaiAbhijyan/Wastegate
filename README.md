# Wastegate

Cheap until it isn't. A System-One gated coding CLI: cheap models first, Fable/Astra only when the gate opens. Skills, MoE-style routing (role × skill × model tier), measured token spend.

## Quickstart

Install (Python ≥ 3.10):

```bash
git clone https://github.com/SaiAbhijyan/Wastegate && cd Wastegate
pip install -e '.[dev]'
```

### Zero-key (works offline)

```bash
wg route  "fix the off-by-one in sliding_windows"     # gate + expert mix, no LLM
wg prompt "fix the off-by-one in sliding_windows"     # composed system prompt (skills + instincts)
wg chat --dry-run                                      # REPL: /route /skills /exit

cp -r tests/fixtures/off_by_one /tmp/obo               # a real off-by-one with a failing test
wg ask --mock --replies tests/fixtures/replies/off_by_one --repo /tmp/obo "fix the off-by-one in sliding_windows"
wg review -1 --note "prefer stdlib over new deps"      # saves an instinct for later turns
```

`wg run` is an alias of `wg ask` (same flags).

### Free live model on your own folder

```bash
export GROQ_API_KEY=...            # free key: https://console.groq.com/keys (never commit it)
cd /path/to/your/project && git status   # start from a clean tree: edits are written in place
wg ask  --live --repo . "fix the failing test in foo.py and add a regression test"
wg chat --live --repo .            # multi-turn; edits applied only because --repo is set
git diff                           # review what it changed; `git checkout .` to undo
```

What `--live --repo` does:
1. gate → route → compose.
2. The driver gets the edit format and a redacted, size-capped view of the folder.
3. Edits are applied only if every edit resolves.
4. The repo's tests run with `python -m pytest -q` before and after.
5. One follow-up asks for a test file if you requested one and none was written.
6. The tester and skeptic review the change.
7. Unresolved items get one pass on the free mid model.

Paid providers are ignored unless you pass `--allow-paid`. Local Ollama (no key): `--live --local`. Other free keys: docs/KEYS.md.

Edits use `<<<REPLACE path / <<<WITH / <<<END` or `<<<FILE path … >>>`, applied only inside `--repo`.

Limits on real folders today:
- Tests are only run with `python -m pytest -q`. Other runners are not supported, and a repo without pytest tests reports a non-zero exit.
- The model sees at most ~24 KB of the folder: the file list plus text files ≤ 8 KB each. Dotfiles and key-like files are skipped.
- Logs go to `./.wastegate/` in the directory you run `wg` from.

Status: Phase 2 (routing, skills, instincts v0, ask/run/chat with dry-run, mock and live). See docs/MISSION.md and docs/PHASE2.md.

## Honest limits

Copied from docs/EVAL_PROTOCOL.md.

- No quality comparison to Fable 5.1 or Astra exists.
- No token or $ savings have been measured. Provider adapters are wired. Three live wiring and contract checks were run (Groq, N=1 each, `results/20260925-live-smoke*.md`). Only the third added the requested regression test. The follow-up and mid-escalation paths are tested with mocks only. None of this is a quality or cost result.
- The offline heuristic gate is a keyword scorer for CI. Its confidences are not calibrated.
- Laya and Jev adapters are request/response shapes only. Live calls are disabled. The Jev wire format is unverified against Jev.
- Built-in skills are our paraphrases of upstream packs. Upstream licenses and SHAs are not yet verified.
- The route labels so far were written by the model, not a human.
