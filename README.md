# Wastegate

Cheap until it isn't. A System-One gated coding CLI: cheap models first, Fable/Astra only when the gate opens. Skills, MoE-style routing (role × skill × model tier), measured token spend.

## Install

### Windows (Anaconda / Miniconda, PowerShell or Anaconda Prompt)

```powershell
conda create -n wastegate python=3.11 -y
conda activate wastegate
git clone https://github.com/SaiAbhijyan/Wastegate
cd Wastegate
git checkout claude/serene-johnson-1o0d5w
pip install -e ".[dev]"
wg --help
wg init
```

### macOS / Linux

```bash
python3.11 -m venv .venv && source .venv/bin/activate      # or conda, as above
git clone https://github.com/SaiAbhijyan/Wastegate && cd Wastegate
git checkout claude/serene-johnson-1o0d5w
pip install -e ".[dev]"
wg --help
wg init
```

`wg init` writes `~/.wastegate/config.toml`. It needs no API key. `git checkout claude/serene-johnson-1o0d5w` is needed until this branch is merged into `main`.

## Quickstart

### 1. Offline, no key: fix a real off-by-one with scripted replies

Windows (PowerShell):

```powershell
Copy-Item -Recurse tests\fixtures\off_by_one $env:TEMP\obo
wg ask --mock --replies tests\fixtures\replies\off_by_one --repo $env:TEMP\obo "fix the off-by-one in sliding_windows"
```

macOS / Linux:

```bash
cp -r tests/fixtures/off_by_one /tmp/obo
wg ask --mock --replies tests/fixtures/replies/off_by_one --repo /tmp/obo "fix the off-by-one in sliding_windows"
```

Expected output includes `edits: windows/__init__.py` and `tests: before=1 after=0`.

Other zero-key commands: `wg route "…"`, `wg prompt "…"`, `wg chat --dry-run` (`/route /skills /exit`), and `wg review -1 --note "prefer stdlib"` (saves an instinct for later turns). `wg run` is an alias of `wg ask`.

### 2. A free live model on your own folder

Get a free Groq key at https://console.groq.com/keys. Set it **only as an environment variable** in your own terminal.

**Never paste keys into chat, issues, or code, and never commit them.** Wastegate reads keys from the environment and redacts them from its logs.

Windows (PowerShell; applies to this terminal session only):

```powershell
$env:GROQ_API_KEY = "<your key>"
cd C:\path\to\your\project
git status                      # start from a clean tree: edits are written in place
wg ask --live --repo . "fix the failing test in foo.py and add a regression test"
git diff                        # review; `git checkout .` to undo
```

macOS / Linux:

```bash
export GROQ_API_KEY="<your key>"
cd /path/to/your/project && git status
wg ask --live --repo . "fix the failing test in foo.py and add a regression test"
git diff
```

`wg chat --live --repo .` does the same thing turn by turn.

### 3. Agent loop: `wg chat --repo` (tool loop + verification gate)

`wg chat --repo DIR` runs a tool loop. System One picks the model (from your live catalog), the tools, `max_steps` (default 8), and whether the verification harness loads. The model then works one action at a time: read, grep, edit, shell (allowlist) or pytest. It can't call the work done without a fresh passing test run after its last edit, and every turn ends with `VERIFICATION: PASS | NOT VERIFIED` and a `Checks:` line. Details: docs/AGENT.md.

Offline, no key:

```bash
cp -r tests/fixtures/off_by_one /tmp/obo
printf 'fix the off-by-one in sliding_windows\n/exit\n' | wg chat --mock --replies tests/fixtures/replies/agent_obo --repo /tmp/obo
wg chat --dry-run --repo /tmp/obo          # shows the model/tools/harness picks, no generation
```

Live: `wg chat --live --repo .` (Groq, OpenRouter `:free`, or `--local` Ollama). `--oneshot` keeps the older single-reply edit path.

What `wg ask --live --repo` does:
1. gate → route → compose.
2. The driver gets the edit format and a redacted, size-capped view of the folder.
3. Edits are applied only if every edit resolves.
4. Your tests run with `python -m pytest -q` before and after.
5. One follow-up asks for a test file if you requested one and none was written.
6. The tester and skeptic review the change.
7. Unresolved items get one pass on the free mid model.

Paid providers are ignored unless you pass `--allow-paid`. Local Ollama (no key): `--live --local`. Other free keys: docs/KEYS.md.

Clear errors instead of tracebacks (exit code 2):
- `--repo` is not a directory → `repo not a directory: …`
- pytest is missing → `pip install pytest`
- no usable key → `no key or --live not set`

A failing test suite is not an error: it is the before/after signal.

## Limits (read before using on real code)

- **pytest only.** Tests are run with `python -m pytest -q` in `--repo`. Other runners are not supported, and a repo without pytest tests reports a non-zero exit before and after.
- **About 24 KB of context.** The model sees the file list plus text files ≤ 8 KB each, up to ~24 KB in total. Dotfiles and key-like files are skipped. On large repos it will not see most of the code.
- **Heuristic gate.** Routing (task kind, complexity, which tier) comes from an offline keyword scorer. It is not calibrated, and Laya and Jev are not wired live.
- **Free models, not frontier.** `--live` uses free-tier models (e.g. Groq `openai/gpt-oss-120b`/`-20b`). No frontier model is ever called, and nothing here claims frontier-level quality.
- Edits are written in place inside `--repo`. Use git to review and undo them.
- The agent loop's shell allowlist is not a sandbox: `python <file>.py` runs arbitrary code from that file. The tamper check is line-level, not a proof. When loaded, the harness skill adds ~16.6 KB to every step's prompt. The agent loop has only been run with mocks so far.
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
