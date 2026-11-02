// Event log: everything SimEnv.log_event() reports (frame.events), newest first.
// Add a line to STYLE to give a new event type its own color and wording.
import { addKo, t } from '../i18n.js';
import { fmtClock, vehicleLabel, APPROACH_NAMES } from '../util.js';
import { $, h } from './dom.js';

addKo({
  'Run started · {scenario} · {controller} · seed {seed} · coverage {coverage}':
    '실행 시작 · {scenario} · {controller} · 시드 {seed} · 내비 데이터 비율 {coverage}',
  '{vehicle} dispatched ({origin} → {destination})': '{vehicle} 출동했어요 ({origin} → {destination})',
  '{vehicle} reached its destination': '{vehicle} 목적지에 도착했어요',
  'east–west': '동서 방향',
  'north–south': '남북 방향',
  'Green for {vehicle} at {junction} ({axis})': '{junction} 신호가 {vehicle}에게 녹색을 줬어요 ({axis})',
  'Green for {vehicle} at {junction} ({axis}, {distance} m out)': '{junction} 신호가 {vehicle}에게 녹색을 줬어요 ({axis}, {distance} m 앞)',
  closure: '폐쇄',
  'Road {edge} closed ({cause})': '{edge} 도로를 폐쇄했어요 ({cause})',
  '{n} vehicles rerouted': '차량 {n}대 경로 변경',
  '{n} stuck': '{n}대 우회 불가',
  'Scheduled event failed: {kind}': '예약된 이벤트가 실패했어요: {kind}',
  'Scheduled event failed: {kind} ({error})': '예약된 이벤트가 실패했어요: {kind} ({error})',
  'Road {edge} reopened': '{edge} 도로를 재개통했어요',
  'Fake-data attack: {n} phantom phones at {junction} {approach} approach': '가짜 데이터 공격: {junction} {approach} 진입로에 가짜 휴대폰 {n}대',
  'Fake-data attack stopped': '가짜 데이터 공격을 멈췄어요',
  'AI recommendation ready': 'AI 추천이 나왔어요',
  'AI recommendation ready (expected {pct}% less delay)': 'AI 추천이 나왔어요 (지연 {pct}% 감소 예상)',
  'AI recommendation approved and applied': 'AI 추천을 승인하고 적용했어요',
  'AI recommendation rejected': 'AI 추천을 거절했어요',
  'AI search failed: {error}': 'AI 탐색이 실패했어요: {error}',
  'unknown error': '알 수 없는 오류',
  'New signal plan applied': '새 신호 계획을 적용했어요',
  'New signal plan applied (cycle {cycle} s)': '새 신호 계획을 적용했어요 (주기 {cycle} s)',
  'No events yet. Scenario events and your actions show up here.': '아직 이벤트가 없어요. 시나리오 이벤트와 직접 조작한 내용이 여기에 나타나요.',
  '{n} event': '{n}건',
  '{n} events': '{n}건',
});

const pct = (v) => (v == null ? '?' : `${Math.round(v * 100)}%`);
const AXIS = { EW: 'east–west', NS: 'north–south' };

function roadClosed(e) {
  const parts = [t('Road {edge} closed ({cause})', { edge: e.edge, cause: t(e.cause || 'closure') })];
  if (e.rerouted != null) parts.push(t('{n} vehicles rerouted', { n: e.rerouted }));
  if (e.unavoidable) parts.push(t('{n} stuck', { n: e.unavoidable }));
  return parts.join(' · ');
}

function preemption(e) {
  const vars = { vehicle: vehicleLabel(e.vehicle), junction: e.junction, axis: t(AXIS[e.axis] || e.axis), distance: e.distance };
  return e.distance != null ? t('Green for {vehicle} at {junction} ({axis}, {distance} m out)', vars) : t('Green for {vehicle} at {junction} ({axis})', vars);
}

export const STYLE = {
  started: ['#3aa0ff', (e) => t('Run started · {scenario} · {controller} · seed {seed} · coverage {coverage}', { scenario: e.scenario, controller: e.controller, seed: e.seed, coverage: pct(e.coverage) })],
  ev_dispatched: ['#ff4d4d', (e) => t('{vehicle} dispatched ({origin} → {destination})', { vehicle: vehicleLabel(e.vehicle), origin: e.origin, destination: e.destination })],
  ev_arrived: ['#22c55e', (e) => t('{vehicle} reached its destination', { vehicle: vehicleLabel(e.vehicle) })],
  preemption: ['#ff7a45', preemption],
  road_closed: ['#fb923c', roadClosed],
  event_failed: ['#ef4444', (e) => (e.error ? t('Scheduled event failed: {kind} ({error})', { kind: e.kind, error: e.error }) : t('Scheduled event failed: {kind}', { kind: e.kind }))],
  road_reopened: ['#22c55e', (e) => t('Road {edge} reopened', { edge: e.edge })],
  attack_started: ['#a855f7', (e) => t('Fake-data attack: {n} phantom phones at {junction} {approach} approach', { n: e.n, junction: e.junction, approach: t(APPROACH_NAMES[e.approach] || e.approach) })],
  attack_stopped: ['#c4a5ff', () => t('Fake-data attack stopped')],
  recommendation_ready: ['#3aa0ff', (e) => (e.improvement_pct != null ? t('AI recommendation ready (expected {pct}% less delay)', { pct: Number(e.improvement_pct).toFixed(1) }) : t('AI recommendation ready'))],
  recommendation_approved: ['#22c55e', () => t('AI recommendation approved and applied')],
  recommendation_rejected: ['#8b9ab3', () => t('AI recommendation rejected')],
  recommendation_failed: ['#ef4444', (e) => t('AI search failed: {error}', { error: e.error || t('unknown error') })],
  plan_applied: ['#22c55e', (e) => (e.plan && e.plan.cycle ? t('New signal plan applied (cycle {cycle} s)', { cycle: Math.round(e.plan.cycle) }) : t('New signal plan applied'))],
};

function generic(e) {
  const rest = Object.entries(e)
    .filter(([k]) => k !== 't' && k !== 'type')
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
    .join(', ');
  return `${e.type.replace(/_/g, ' ')}${rest ? ` · ${rest}` : ''}`;
}

export function describeEvent(e) {
  const style = STYLE[e.type];
  try {
    return { color: style ? style[0] : '#8b9ab3', text: style ? style[1](e) : generic(e) };
  } catch {
    return { color: '#8b9ab3', text: generic(e) };
  }
}

export class EventLog {
  constructor(ctx) {
    this.root = $('#events');
    this.count = $('#events-count');
    this.n = 0;
    this.max = 250;
    this.empty();
    ctx.bus.on('hello', (msg) => {
      this.clear();
      for (const e of msg.events || []) this.add(e, false);
    });
    ctx.bus.on('session', () => this.clear());
    ctx.bus.on('frame', (f) => {
      for (const e of f.events || []) this.add(e, true);
    });
  }

  empty() {
    this.root.innerHTML = '';
    this.root.append(h('li', { class: 'empty' }, t('No events yet. Scenario events and your actions show up here.')));
  }

  clear() {
    this.n = 0;
    this.empty();
    this.count.textContent = '';
  }

  add(e, fresh) {
    if (this.n === 0) this.root.innerHTML = '';
    const { color, text } = describeEvent(e);
    const li = h('li', { class: fresh ? 'fresh' : '' }, h('time', {}, fmtClock(e.t)), h('span', { class: 'edot', style: { background: color } }), h('span', {}, text));
    this.root.prepend(li);
    this.n++;
    while (this.root.children.length > this.max) this.root.lastChild.remove();
    this.count.textContent = t(this.n === 1 ? '{n} event' : '{n} events', { n: this.n });
  }
}
