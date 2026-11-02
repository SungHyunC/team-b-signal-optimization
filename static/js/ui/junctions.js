// Per-junction signal state: a mini intersection (arms colored by what each approach sees),
// the current state and how long it has been shown, the earliest possible change, queues,
// and an "EV priority" badge during emergency preemption. Click a row to fly the camera there.
import { addKo, lang, t } from '../i18n.js';
import { $, h } from './dom.js';

addKo({
  'Fly the camera to {j}': '{j} 교차로로 카메라 이동',
  'East–West': '동서',
  'North–South': '남북',
  green: '녹색',
  yellow: '황색',
  'all-red': '전적색',
  'next change in ≥ {s} s': '다음 변경까지 ≥ {s} s',
  'can change now': '지금 변경 가능',
  'queue W {W} · E {E} · N {N} · S {S}': '대기열 서 {W} · 동 {E} · 북 {N} · 남 {S}',
  'EV priority · {axis}': '긴급차량 우선 · {axis}',
});

const COLOR = { G: '#22c55e', Y: '#fbbf24', R: '#ef4444' };
const PART = { G: 'green', Y: 'yellow', AR: 'all-red' };
const AXIS = { EW: 'East–West', NS: 'North–South' };
const word = (names, key) => (names[key] ? t(names[key]) : key);

function miniIntersection() {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 54 54');
  const rect = (x, y, w, hh, fill, cls) => {
    const r = document.createElementNS(ns, 'rect');
    Object.entries({ x, y, width: w, height: hh, rx: 2, fill }).forEach(([k, v]) => r.setAttribute(k, v));
    if (cls) r.dataset.arm = cls;
    svg.append(r);
    return r;
  };
  rect(0, 0, 54, 54, '#0a111d');
  rect(19, 0, 16, 54, '#28303d');
  rect(0, 19, 54, 16, '#28303d');
  // Arms: the stop bar each approach sees (W arm on the left, N on top).
  const arms = {
    W: rect(3, 28, 13, 5, COLOR.R, 'W'),
    E: rect(38, 21, 13, 5, COLOR.R, 'E'),
    N: rect(21, 3, 5, 13, COLOR.R, 'N'),
    S: rect(28, 38, 5, 13, COLOR.R, 'S'),
  };
  return { svg, arms };
}

export class JunctionPanel {
  constructor(ctx) {
    this.root = $('#junctions');
    this.rows = new Map();
    for (const j of ctx.meta.junctions) {
      const { svg, arms } = miniIntersection();
      const name = h('div', { class: 'jname' }, j);
      const state = h('div', { class: 'jstate' }, '–');
      const meta = h('div', { class: 'jmeta' }, '');
      const row = h('div', { class: 'jrow', title: t('Fly the camera to {j}', { j }) }, svg, h('div', {}, name, state, meta));
      row.addEventListener('click', () => ctx.camera.fly(j));
      this.root.append(row);
      this.rows.set(j, { row, arms, name, state, meta });
    }
    ctx.bus.on('frame', (f) => this.update(f));
  }

  update(frame) {
    const signals = frame.signals || {};
    const queues = (frame.kpi && frame.kpi.queues) || {};
    for (const [j, r] of this.rows) {
      const s = signals[j];
      if (!s) continue;
      for (const [side, arm] of Object.entries(r.arms)) arm.setAttribute('fill', COLOR[(s.colors || {})[side]] || '#444');
      const [axis, part] = String(s.signal || '').split('_');
      const color = part === 'G' ? 'G' : part === 'Y' ? 'Y' : 'R';
      r.state.innerHTML = '';
      r.state.append(
        h('span', { class: `c-${color}` }, `${word(AXIS, axis)} ${word(PART, part)}`),
        ' · ',
        h('b', {}, `${Math.round(s.time_in_state || 0)} s`),
      );
      const q = queues[j] || {};
      const qText = t('queue W {W} · E {E} · N {N} · S {S}', { W: q.W ?? 0, E: q.E ?? 0, N: q.N ?? 0, S: q.S ?? 0 });
      const change = s.min_time_to_change > 0 ? t('next change in ≥ {s} s', { s: Math.ceil(s.min_time_to_change) }) : t('can change now');
      r.meta.textContent = `${change} · ${qText}`;
      r.name.innerHTML = '';
      r.name.append(j);
      // preempted_by is the axis given priority (EW / NS): spelled out in Korean.
      if (s.preempted_by) r.name.append(h('span', { class: 'badge red' }, t('EV priority · {axis}', { axis: lang === 'ko' ? word(AXIS, s.preempted_by) : s.preempted_by })));
      r.row.classList.toggle('preempt', !!s.preempted_by);
    }
  }
}
