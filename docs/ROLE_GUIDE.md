# Role guide · 역할별 수정 가이드

The first version of the whole prototype is built end to end, on purpose: now that everything
runs, each of us can see what is weak in our own part and fix it. This page says where your
code lives, what "done" means (from Aditya's role packages), and good next steps.
Detailed notes per area are in [`docs/roles/`](roles/).

프로토타입 전체를 일단 끝까지 동작하게 만들어 두었습니다. 이제 각자 자기 영역에서 무엇이 부족한지
직접 돌려 보며 고치면 됩니다. 아래는 담당 폴더, 완료 기준(Aditya 역할 문서 기준), 다음 할 일입니다.

## Common workflow · 공통 작업 순서

```bash
git pull
git checkout -b <your-name>/<topic>        # e.g. doyoung/biased-sampling
python -m teamb twin                       # watch your change live
python -m pytest                           # must pass before you push
git push -u origin <your-name>/<topic>     # then open a pull request
```

- After a change that shows in the twin is merged to `main`, refresh the online demo with
  `python -m teamb.twin.site deploy` (~3 min; details in [`roles/twin.md`](roles/twin.md#online-demo-github-pages)).
- Stay inside your folders; if you need a change in someone else's part, ask in Discord or open an issue.
- Keep the data contracts in [`ARCHITECTURE.md`](ARCHITECTURE.md): adding fields is fine, renaming or removing breaks others.
- AI coding tools are allowed for everything (research, organizing, code).

## Seong Hyeon (Joshua) — Software & integration · 소프트웨어·통합

| | |
|---|---|
| Folders | `teamb/network/`, `teamb/sim/`, `teamb/safety/`, `teamb/controllers/base.py`, `teamb/controllers/fixed_time.py`, `teamb/twin/` |
| Tests | `tests/test_core.py` (NET-01, SIG-01, SIG-02, REP-01, PERF-01), `tests/test_twin.py`, `tests/test_site.py` |
| Done when | one-command reproducible baseline on all four junctions · fixed-time vs coordinated comparison · validated signal transitions · exported results · setup README · demo recording |
| Next | a proper `SimEnv` "fast" option (no sensors / sparse KPIs) to replace the wrappers in `controllers/fast_env.py` · read departed/arrived/time from one simulation subscription · pedestrian phases and protected left turns · twin: split-screen A/B compare, several sessions, demo script for Nov 5 (`python -m teamb.twin.vendor` before going offline) |
| Notes | [`roles/twin.md`](roles/twin.md) |

## Doyoung — Data & evaluation · 데이터·평가

| | |
|---|---|
| Folders | `teamb/sensors/`, `teamb/evaluation/`, `teamb/experiments/` |
| Tests | `tests/test_data.py` |
| Done when | documented datasets and data dictionary · sampling generator · scenario matrix · reproducible KPI extraction · paired analysis · evidence matrix and result tables |
| Next | 20-seed runs for the primary comparison (3 seeds now ≈ pilot) · position noise and reporting delay for probe data · counterfactual (no-event) runs for recovery time (`--counterfactual`) · catch small attacks right after the detector zone was full · estimation error vs coverage chart for Report 3 · Databricks questions (geospatial cost, MLOps) · verify Boston/Jeju/Busan figures in the evidence register |
| Notes | [`roles/data-evaluation.md`](roles/data-evaluation.md), [`results/`](results/) |

## Yunseong — AI & security · AI·보안

| | |
|---|---|
| Folders | `teamb/controllers/` (actuated, max-pressure, AI recommender, RL), `models/` |
| Tests | `tests/test_controllers.py` |
| Done when | documented algorithm choice and baselines · controller adapters · model/reward specs · trained RL checkpoint · holdout comparison with uncertainty · threat model and failure tests |
| Next | AI recommender: most of its gain comes from the Webster seed plan and it searches at 600 s (≈ 80 % of peak) — search later / re-optimize, speed up trials · probe max-pressure counts the whole link, not the last 100 m · RL ties max-pressure, try reward shaping or SUMO-RL · max-pressure uses all upstream vs stopped downstream cars (`measure="queue"` is the textbook version) · MPC, neighbor-aware MARL · more attack types (replay, stale timestamps) · Tesla questions on signal perception and V2X |
| Notes | [`roles/ai-security.md`](roles/ai-security.md), [`../models/README.md`](../models/README.md) |

## Aditya — Scenarios & analysis · 시나리오·분석 (with Doyoung)

| | |
|---|---|
| Folders | `teamb/scenarios/`, `teamb/demand/`, `teamb/api/`, `teamb/analysis/` |
| Tests | `tests/test_scenarios.py` |
| Done when | emergency and disaster scenarios run reproducibly · impact & cost-benefit table for Report 4's CSUEB section · signal-data API documented |
| Next | revisit the assumptions: `road_closure` lets 30 % of eastbound through traffic avoid the corridor, emergency vehicles can't pass queues (SUMO bluelight device off → preemption benefit is an upper bound), CO₂ priced at $190/t (set 0 to follow the 2025 USDOT guidance) · more first-responder cases (police, search & rescue) and landslides · a mock navigation app on the signal-data API · ideas from the Nov 5 joint session |
| Notes | [`roles/scenarios-analysis.md`](roles/scenarios-analysis.md), [`scenarios.md`](scenarios.md) |

## Integration checkpoints · 통합 체크포인트

1. Agree on SUMO geometry, phase indexing, detector schema and scenario IDs → **done in v1** (see ARCHITECTURE.md)
2. Run the same baseline scenario with common KPI definitions and confirmed safety checks
3. Freeze holdout scenarios before choosing the final algorithm; report paired outcomes
4. Review evidence limitations, operational risks and what we claim in the presentation
