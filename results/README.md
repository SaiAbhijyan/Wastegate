# results/

Raw result files. Each one says what it is and what it is not. None of them is a product benchmark yet.

## Label-before-code order (route_quality v1)
`e350e82` (labels.md frozen) precedes `8be83f6` (heuristic.py added). Verify: `git merge-base --is-ancestor e350e82 8be83f6 && echo ok`

## Frozen heuristic
`src/wastegate/systemone/heuristic.py` is frozen after session 1. `tests/test_heuristic_frozen.py` strips the one-line FROZEN
header and checks the rest is byte-identical to the sha256 recorded in `20260924-dev-selflabel.md`.
Changing cues requires a new label set written by a human who has not read the file, a new
run, and an explicit replacement of that results file. The same commit must say so.
