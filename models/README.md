# models/

Trained artifacts that controllers load at run time. Owner: AI & security (Yunseong).

| File | Used by | Made by |
|---|---|---|
| `rl_qtable.json` | `rl` controller (`teamb/controllers/rl.py`) | `python -m teamb.controllers.rl_train` |

## rl_qtable.json

A tabular Q-function for the shared junction policy: 288 states × 2 actions (keep / switch),
plus visit counts, the feature definition, training metadata (episodes, seeds, wall time,
hyper-parameters, the per-episode training curve) and a SHA-256 checksum.

- **Retrain** (about 5–15 min, 2 SUMO runs at a time):
  `python -m teamb.controllers.rl_train` (defaults: 60 episodes × 1800 s)
  (`--resume` continues from the current file; `--help` lists every knob).
- **Integrity**: `QTable.load` refuses a file whose checksum or feature definition does not
  match the code. This catches accidental edits and version drift; it is *not* a signature —
  anyone who can write this folder can also recompute the checksum. A deployed system would
  sign artifacts with a key kept outside the repo (see `docs/roles/ai-security.md`).
- **Held-out seeds**: training uses seeds 1000+, experiments use small seeds, so evaluation
  runs never see training traffic.
- Small enough (~17 KB) to commit; regenerate it instead of editing it by hand.
