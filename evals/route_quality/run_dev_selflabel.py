"""One-shot dev check: heuristic `kind` on the frozen holdout 20.

Self-labeled dev set, author=model, not a product benchmark. Raw rows only:
no CI / ECE / Brier (Phase 3). Misses are reported, not fixed, in session 1.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

from wastegate.labels import load_labels
from wastegate.systemone.base import GATE_QUESTIONS
from wastegate.systemone.heuristic import HeuristicSystemOne

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "evals/route_quality/labels.md"


def main(out_path: str) -> None:
    rows = [r for r in load_labels(LABELS) if r.split == "holdout"]
    s1 = HeuristicSystemOne()
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    heur = hashlib.sha256((ROOT / "src/wastegate/systemone/heuristic.py").read_bytes()).hexdigest()
    lines = [
        "# 2026-09-24 dev check: heuristic kind on holdout 20",
        "",
        "**self-labeled dev set, author=model, not a product benchmark.**",
        "",
        f"- git HEAD at run: `{sha}`",
        f"- labels.md sha256: `{hashlib.sha256(LABELS.read_bytes()).hexdigest()}`",
        f"- heuristic.py sha256: `{heur}`",
        "- backend: heuristic (keyword rules, uncalibrated). No LLM, Laya, or Jev involved.",
        "- run count on this holdout: 1. Misses left unfixed this session.",
        "",
        "| id | prompt | label | predicted | top prob | hit |",
        "|---|---|---|---|---|---|",
    ]
    hits = 0
    for r in rows:
        a = s1.decide(r.prompt, GATE_QUESTIONS)["kind"]
        hit = a.value == r.kind
        hits += hit
        lines.append(f"| {r.id} | {r.prompt} | {r.kind} | {a.value} | {a.confidence:.2f} | {'Y' if hit else 'N'} |")
    lines += ["", f"Hits: {hits}/{len(rows)}. N=20 and the labels were written by the model, so this is not evidence of routing quality.", ""]
    Path(out_path).write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
