# Team B documentation

Start with the [project README](../README.md) (install, commands, results). This page lists every
document in `docs/` by what you want to do. Files keep their old paths, so existing links still work.

## Use and extend the prototype

| Document | What it covers |
|---|---|
| [Architecture](ARCHITECTURE.md) | How network, simulation, safety supervisor, controllers, sensors and twin connect; data contracts |
| [Scenario catalog](scenarios.md) | Every scenario, its demand, events and parameters · 시나리오 목록 |
| [Role guide](ROLE_GUIDE.md) | Who changes what next · 역할별 수정 가이드 |
| [Digital twin](roles/twin.md) | Live 3D twin, server API, online demo (GitHub Pages) |
| [AI & security](roles/ai-security.md) | Controllers, AI recommender, RL, fake-data defenses |
| [Data & evaluation](roles/data-evaluation.md) | Sensors, metrics, batch experiments and statistics |
| [Scenarios & analysis](roles/scenarios-analysis.md) | Demand, events, signal-data API, impact and cost-benefit |

## Deploy and present

| Document | What it covers |
|---|---|
| [Cloud live SUMO deployment](cloud-live-sumo-deployment.md) | The Docker/Render service: deployed state, access token, cookies, image, limits |
| [Presentation-day demo runbook](presentation-day-demo-runbook.md) | Which link to put on the QR code, run of show, preflight checklist |
| [Final presentation brief](final-presentation-brief.md) | Slide-by-slide script and Q&A |
| [Final project handoff](final-project-handoff.md) | Release state, Windows walkthrough, validated findings |

## Results and research

Headline numbers come from the 30-seed studies, whose aggregate data is committed under
[results/studies/](results/studies/README.md). The 3-seed v1 tables are pilot numbers.

| Document | What it covers |
|---|---|
| [Study data archive](results/studies/README.md) | Reports, per-run summary tables and audits of the 30-seed studies (Actions artifacts expire) |
| [Final engineering review](final-engineering-review.md) | Roadmap, validated results, why the experimental controller was rejected |
| [Robustness and sensitivity review](robustness-and-sensitivity-review.md) | 75 / 100 / 125 % demand, 540 strict-valid runs |
| [Robustness study design](robustness-and-sensitivity.md) | How the demand-sensitivity study was set up and run |
| [Lesson 1 validation runbook](lesson1-validation-runbook.md) | Reproducing the 180-run paired-seed baseline |
| [Congestion controller pilot review](congestion-controller-pilot-review.md) | First spillback-aware variant: 3-seed pilot, held back |
| [Spillback penalty calibration review](spillback-penalty-calibration-review.md) | 24-run calibration that picked the 1.25 penalty |
| [Independent confirmation decision](independent-controller-confirmation-review.md) | 360-run holdout test: experimental controller rejected |
| [Prototype v1 results](results/README.md) | 3-seed pilot tables for all controllers and scenarios, with per-experiment reports |

## Program documents

| File | What it is | Language |
|---|---|---|
| [topic-candidates_2026-10-12_KR.pdf](topic/topic-candidates_2026-10-12_KR.pdf) | Sub-topic candidates under the main theme · 세부 주제 후보 | KR |
| [chosen-topic_traffic-signal-optimization_KR.pdf](topic/chosen-topic_traffic-signal-optimization_KR.pdf) | Our chosen topic (one page) · 확정 주제 | KR |
| [report-1_research-plan_2026-10-13_KR.pdf](activity-reports/report-1_research-plan_2026-10-13_KR.pdf) | Report 1: Research & Plan, first version · 활동보고서 ❶ 조사·계획 | KR |
| [report-1_research-plan_revised_2026-10-15_KR.pdf](activity-reports/report-1_research-plan_revised_2026-10-15_KR.pdf) | Report 1, revised (latest) · ❶ 수정본(최신) | KR |
| [Team_B_Comprehensive_Traffic_AI_Research_Report.pdf](research/Team_B_Comprehensive_Traffic_AI_Research_Report.pdf) | Research report by Aditya · Aditya 연구보고서 | EN |
| [research/](research/) `Team_B_*.docx` | Role packages for software, big data and AI, by Aditya · 역할 문서 3종 | EN |
| [prototype-plan_EN.pdf](plans/prototype-plan_EN.pdf) | Prototype plan (optional) | EN |
| [prototype-plan_KR.pdf](plans/prototype-plan_KR.pdf) | 프로토타입 제작 계획 | KR |

### Program schedule (from the program book)

| Date | Plan |
|---|---|
| Nov 1 (Sun) | Depart Incheon, arrive San Francisco |
| Nov 2 (Mon) | KIC Silicon Valley, **Google** — Seong Hyeon's questions |
| Nov 3 (Tue) | **Tesla** Fremont Factory, Apple Park, expert panel — Yunseong's questions |
| Nov 4 (Wed) | Amazon Tracy fulfillment center, **Databricks** — Doyoung's questions |
| Nov 5 (Thu) | CSU East Bay: lectures, joint session with Aditya, **team presentation 16:00** |
| Nov 6 (Fri) | Pensive, depart San Francisco |
| Nov 8 (Sun) | Arrive in Korea |
