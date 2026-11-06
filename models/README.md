# models/

Trained artifacts that controllers load at run time. Owner: AI & security (Yunseong).

| File | Used by | Made by |
|---|---|---|
| `rl_qtable.json` | `rl` controller (`teamb/controllers/rl.py`), default `model_path` | `python -m teamb.controllers.rl_train` |
| `rl_qtable_v1_rush_hour.json` | `rl` with `{"model_path": "models/rl_qtable_v1_rush_hour.json"}` | the first committed model, kept unchanged |

## rl_qtable.json

A tabular Q-function for the shared junction policy: 288 states × 2 actions (keep / switch),
plus visit counts, the feature definition, training metadata (episodes, seeds, wall time,
hyper-parameters, the training curve) and a SHA-256 checksum.

- **Retrain** (about 5–15 min, 2 SUMO runs at a time):
  `python -m teamb.controllers.rl_train` (defaults: 60 episodes × 1800 s of rush hour)
  (`--resume` continues from the current file; `--help` lists every knob).
- **Much more data**: sample scenarios and demand per episode and run the episodes on Modal,
  e.g. `teamb train-rl --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak
  --demand-range 0.75,1.25 --end full --episodes 1200 --backend modal --workers 64 --max-minutes 120
  --out results/rl/mixed.json`. Write to a scratch `--out` first, compare it on evaluation
  seeds (< 1000) against this file, and only then replace `rl_qtable.json`.
- **Integrity**: `QTable.load` refuses a file whose checksum or feature definition does not
  match the code. This catches accidental edits and version drift; it is *not* a signature —
  anyone who can write this folder can also recompute the checksum. A deployed system would
  sign artifacts with a key kept outside the repo (see `docs/roles/ai-security.md`).
- **Held-out seeds**: training uses seeds 1000+, experiments use seeds below 1000, so evaluation
  runs never see training traffic.
- **Visit counts**: files trained with the current `rl_train` count each collected transition
  once (`meta.visit_unit = "transitions"`). Older files (no `visit_unit`) counted every replay
  update, up to 30× more. The controller's low-confidence fallback (`fallback_min_visits`,
  default 20) compares against these counts.
- Small enough (~17 KB) to commit; regenerate it instead of editing it by hand.

## rl_qtable_v1_rush_hour.json

A byte-for-byte copy of the model the first results were produced with (60 episodes × 1800 s,
rush hour only, 2 workers, seed 0). It keeps the "trained only on rush hour" lesson reproducible
after `rl_qtable.json` is retrained:

- the original behaviour: `{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}`
- with the low-confidence fallback: `{"model_path": "models/rl_qtable_v1_rush_hour.json"}`

Relative model paths resolve from the working directory first, then from the repo root.
