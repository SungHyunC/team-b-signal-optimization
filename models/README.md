# models/

Trained artifacts that controllers load at run time. Owner: AI & security (Yunseong).

| File | Used by | Made by |
|---|---|---|
| `rl_qtable.json` | `rl` controller (`teamb/controllers/rl.py`), default `model_path` | `python -m teamb.controllers.rl_train` |
| `rl_qtable_v1_rush_hour.json` | `rl` with `{"model_path": "models/rl_qtable_v1_rush_hour.json"}` | the first committed model, kept unchanged |

## rl_qtable.json

The default model since November 2026: a tabular Q-function for the shared junction policy with
the **v2 features** (576 states = the v1 state × a "green blocked" bit: after 15 s of green, at
least half of the green axis' cars, and at least 4, are still stopped) × 2 actions, plus visit
counts (`visit_unit = "transitions"`), the feature definition, training metadata and a SHA-256
checksum (`2d1f2c0d…` for the file itself).

- **Training**: 2,000 full-length episodes on Modal (48 containers, about 35 min), each drawing one
  of rush_hour, special_event, emergency, road_closure, sinkhole_cross, earthquake, off_peak and a
  demand scale U(0.75, 1.25); seeds 1,001,000+ (training seed 1), replay buffer 96 episodes.
- **Selection**: chosen on validation seeds 900-909 (never used for training or the final test)
  against three other candidates trained the same week: v1 features × 2,000 episodes, this model
  resumed for 3,840 more episodes at demand 0.75-1.4, and a fresh v2 run of 5,760 episodes. More
  episodes did not help the tabular policy; see
  [the RL retraining study](../docs/results/studies/rl-retraining-2026-11/README.md).
- **Result** on the final test seeds 201-230 (7 scenarios × demand 0.75/1.0/1.25): the flood
  that broke the first model (169 s/veh at 100 % demand) drops to 87 s/veh, about max-pressure's
  88 s; it beats max-pressure off-peak and at the stadium surge, but loses in the earthquake.
  Details in [the confirmation study](../docs/results/studies/controller-confirmation-2026-11/README.md).

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
  update, up to 30× more. `--resume` from such a file keeps those counts and adds transitions
  on top, so it saves `visit_unit = "mixed"` (and keeps that label on later resumes); retrain
  from scratch for pure transition counts. The controller's low-confidence fallback
  (`fallback_min_visits`, default 20) compares against these counts, so on a legacy or mixed
  file it trusts states that saw fewer real transitions.
- Small enough (~136 KB) to commit; regenerate it instead of editing it by hand.

## rl_qtable_v1_rush_hour.json

A byte-for-byte copy of the model the first results were produced with (60 episodes × 1800 s,
rush hour only, 2 workers, seed 0). It keeps the "trained only on rush hour" lesson reproducible
after `rl_qtable.json` is retrained:

- the original behaviour: `{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}`
- with the low-confidence fallback: `{"model_path": "models/rl_qtable_v1_rush_hour.json"}`

Relative model paths resolve from the working directory first, then from the repo root.
