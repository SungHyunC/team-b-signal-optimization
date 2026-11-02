// SPaT panel: polls the real signal-data API (GET /api/v1/spat, teamb/api/signal_data.py) once
// a second and shows what a navigation app would receive: per junction, the color each approach
// sees, how long it has been shown and the earliest time it can change. The online demo has no
// API server, so there it shows the same fields from the recorded frames.
import { addKo, t } from '../i18n.js';
import { $, h } from './dom.js';

addKo({
  'waiting for the simulation…': '시뮬레이션을 기다리는 중…',
  'raw JSON (what an app downloads)': '원본 JSON (앱이 내려받는 내용)',
  'The API answers while the live twin runs (python -m teamb twin)': '실시간 트윈(python -m teamb twin)이 실행 중일 때 API가 응답해요',
  'from the recording': '녹화 데이터',
  'open ↗': '열기 ↗',
  'Starting the simulation…': '시뮬레이션을 시작하는 중…',
  'No simulation running.': '실행 중인 시뮬레이션이 없어요.',
  'The API answered {status}.': 'API가 {status}로 응답했어요.',
  'Server not reachable.': '서버에 연결할 수 없어요.',
  'approach colors': '진입로별 신호',
  state: '상태',
  shown: '유지 시간',
  'When the current state is expected to end (the API also gives min/max)': '지금 신호가 끝날 것으로 예상되는 시점 (API는 최소/최대도 알려줘요)',
  'changes in': '변경까지',
  '{approach} approach: {color}': '{approach} 진입로: {color}',
});

const ENDPOINT = '/api/v1/spat';

export class SpatPanel {
  constructor(ctx) {
    this.ctx = ctx;
    this.card = $('#spat-panel');
    this.timer = null;
    this.visible = true;
    this.time = h('span', {});
    this.message = h('div', { class: 'act-note' }, t('waiting for the simulation…'));
    this.table = h('table', {});
    this.pre = h('pre', {});
    this.details = h('details', {}, h('summary', { class: 'act-note' }, t('raw JSON (what an app downloads)')), this.pre);
    const link = ctx.static
      ? h('span', { class: 'act-note', title: t('The API answers while the live twin runs (python -m teamb twin)') }, t('from the recording'))
      : h('a', { href: ENDPOINT, target: '_blank', rel: 'noopener' }, t('open ↗'));
    $('#spat').append(h('div', { class: 'endpoint' }, h('span', {}, h('code', {}, `GET ${ENDPOINT}`), this.time), link), this.message, this.table, this.details);
    $('#spat-head').addEventListener('click', () => {
      this.card.classList.toggle('collapsed');
      this.poll();
    });
    ctx.bus.on('view', (name) => {
      this.visible = name === 'live';
    });
    this.live = false;
    ctx.bus.on('status', (s) => {
      this.live = ['running', 'paused'].includes(s.state);
      if (!this.live) this.render(null, t(s.state === 'loading' ? 'Starting the simulation…' : 'No simulation running.'));
    });
    this.render(null, t('waiting for the simulation…'));
    if (ctx.static) {
      let shown = 0;
      ctx.bus.on('frame', (f) => {
        const now = performance.now();
        if (now - shown < 1000 || this.card.classList.contains('collapsed') || !f.signals) return;
        shown = now;
        this.render({ t: f.t, source: 'recording', junctions: f.signals });
      });
      return;
    }
    this.poll();
  }

  async poll() {
    clearTimeout(this.timer);
    if (this.ctx.static) return;
    const open = !this.card.classList.contains('collapsed') && this.visible && !document.hidden && this.live;
    if (open) {
      try {
        const r = await fetch(ENDPOINT, { cache: 'no-store' });
        if (r.status === 503) this.render(null, t('No simulation running.'));
        else if (!r.ok) this.render(null, t('The API answered {status}.', { status: r.status }));
        else this.render(await r.json());
      } catch {
        this.render(null, t('Server not reachable.'));
      }
    }
    this.timer = setTimeout(() => this.poll(), 1000);
  }

  render(data, message) {
    this.message.hidden = !!data;
    this.table.hidden = this.details.hidden = !data;
    if (!data) {
      this.message.textContent = message || '';
      this.time.textContent = '';
      return;
    }
    this.time.textContent = ` · t = ${Math.round(data.t)} s`;
    this.table.innerHTML = '';
    this.table.append(h('tr', {}, h('th', {}, ''), h('th', {}, t('approach colors')), h('th', {}, t('state')), h('th', {}, t('shown')), h('th', { title: t('When the current state is expected to end (the API also gives min/max)') }, t('changes in')), h('th', {}, '')));
    for (const [j, s] of Object.entries(data.junctions || {})) {
      const colors = s.colors || {};
      // Newer API versions predict the end of the state (state_ends_in_s: {min, max, likely}).
      const ends = s.state_ends_in_s || {};
      const changes = typeof ends.likely === 'number' ? `~${Math.round(ends.likely)} s` : `≥ ${Math.ceil(s.min_time_to_change ?? 0)} s`;
      const range = typeof ends.min === 'number' ? `min ${Math.round(ends.min)} s${typeof ends.max === 'number' ? `, max ${Math.round(ends.max)} s` : ''}` : '';
      this.table.append(
        h('tr', {},
          h('td', {}, h('b', {}, j)),
          h('td', {}, ...['W', 'E', 'N', 'S'].map((a) => h('span', { title: t('{approach} approach: {color}', { approach: a, color: colors[a] }) }, h('span', { class: `lamp ${colors[a] || 'R'}` }), a, ' '))),
          h('td', {}, s.signal),
          h('td', {}, `${Math.round(s.time_in_state ?? 0)} s`),
          h('td', { title: range }, changes),
          h('td', {}, s.preempted_by ? h('span', { class: 'badge red' }, `EV ${s.preempted_by}`) : '')),
      );
    }
    if (this.details.open) this.pre.textContent = JSON.stringify(data, null, 1);
  }
}
