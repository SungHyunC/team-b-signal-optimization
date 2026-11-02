# Results · 실험 결과 (prototype v1, 2026-11-02)

Pilot numbers: 3 paired demand seeds per row, synthetic demand, SUMO 1.28. Delay = mean SUMO
time loss of trips that start after the 900 s warm-up (s/veh, lower is better); `±` = half-width
of the 95 % t-interval; Δ = paired improvement vs fixed-time on the same seeds. Read unfinished
trips next to delay (PERF-01). Full tables, p-values and sensor accuracy are in the linked reports.

파일럿 수치입니다(행마다 시드 3개, 합성 수요). 발표에 인용하기 전에 시드를 늘려 다시 돌려 주세요.

## 1. Normal peak — rush hour · 출퇴근 ([v1-main](v1-main.md), runs to 2700 s)

| Controller | Delay (s/veh) | Δ vs fixed-time | p95 travel time (s) | Unfinished |
|---|---:|---:|---:|---:|
| fixed_time | 71.0 ± 10.5 | — | 273 | 10.3 % |
| coordinated | 48.4 ± 2.2 | −31.8 % | 255 | 8.3 % |
| ai_recommender | 37.6 ± 1.8 | −47.0 % | 184 | 7.9 % |
| actuated | 30.7 ± 5.0 | −56.7 % | 173 | 7.2 % |
| rl | 30.6 ± 4.3 | −56.7 % | 166 | 7.1 % |
| max_pressure | 29.2 ± 2.9 | −58.7 % | 168 | 6.9 % |

## 2. Emergency vehicles · 응급차량 ([v1-main](v1-main.md))

Emergency-vehicle travel time drops from 110 s (fixed-time) to ≈ 90–95 s with adaptive control plus
preemption, while everyone else's delay stays close to the rush-hour numbers above
(max-pressure 29.8 s, RL 31.7 s, AI recommender 39.1 s vs 72.1 s fixed-time).
응급차 통행시간 110초 → 약 90~95초, 일반 차량 지연은 거의 그대로입니다.

## 3. Flood closure J2 → J3 · 침수 도로폐쇄 ([v1-closure](v1-closure.md), full 5400 s)

| Controller | Delay (s/veh) | Δ vs fixed-time | Unfinished |
|---|---:|---:|---:|
| fixed_time | 119.6 ± 3.7 | — | 6.5 % |
| actuated | 83.8 ± 1.2 | −29.9 % | 2.3 % |
| max_pressure | 94.7 ± 13.7 | −20.8 % | 2.3 % |
| rl | 170.2 ± 101.3 | **+42 % (worse, unstable)** | 2.9 % |

**Finding:** the RL controller was trained only on rush hour. When the road network changes it
can break down badly (huge spread across seeds), while the rule-based controllers stay robust.
This is the out-of-distribution risk Yunseong's role package warns about — a good point for
Report 3 and a clear next step (train on closures, or fall back when the network changes).
**발견:** 출퇴근만 학습한 RL은 도로가 막히는 상황에서 고정신호보다 나빠질 수 있습니다(학습하지 않은 상황에 대한 취약성).

## 4. Fake navigation data · 가짜 내비 데이터 ([v1-security](v1-security.md), [defense](v1-security-defense.md))

99 phantom "phones" report a jam on J2's north approach; 25 % of vehicles share navigation data.

| Controller | Delay (s/veh) | Unfinished |
|---|---:|---:|
| fixed_time | 79.5 ± 28.6 | 4.0 % |
| max_pressure (loop detectors) | 29.4 ± 5.4 | 2.3 % |
| max_pressure_probe (navigation data only, no defense) | **175.6 ± 57.8** | 8.6 % |
| max_pressure_probe + detector cross-check (`defense: true`) | 48.2 ± 12.7 | 2.7 % |

**Finding:** a controller that trusts navigation data alone can be steered by fake reports into
worse-than-fixed-time chaos; cross-checking against loop detectors removes most of the damage.
**발견:** 내비 데이터만 믿는 제어는 가짜 신고에 크게 흔들리고, 감지기 교차검증으로 대부분 막을 수 있습니다.

## 5. Sampling bias · 표본 편향 ([coverage sweep](coverage-sweep-report.md), 1 seed)

When probe sampling over-represents arterial drivers, a probe-fed controller starves the cross
streets (62 s vs 38 s delay with even sampling). See also [sample-report](sample-report.md) for
sensor estimation accuracy.

## Reproduce

```bash
python -m teamb.experiments run --name v1-main --scenarios rush_hour,emergency \
  --controllers fixed_time,coordinated,actuated,max_pressure,ai_recommender,rl --seeds 1-3 --end 2700 \
  --controller-params '{"ai_recommender": {"auto_approve": true}}'
python -m teamb.experiments run --name v1-closure --scenarios road_closure --controllers fixed_time,actuated,max_pressure,rl --seeds 1-3
python -m teamb.experiments run --name v1-security --scenarios fake_data_attack --controllers fixed_time,max_pressure,max_pressure_probe --coverages 25 --seeds 1-3
python -m teamb.experiments run --name v1-security-defense --scenarios fake_data_attack --controllers max_pressure_probe --coverages 25 --seeds 1-3 \
  --controller-params '{"max_pressure_probe": {"defense": true}}'
python -m teamb.analysis.impact results/experiments/v1-main   # cost-benefit table
```
