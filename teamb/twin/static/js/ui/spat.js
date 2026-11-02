// SPaT panel: polls the real signal-data API (GET /api/v1/spat, teamb/api/signal_data.py) once
// a second and shows what a navigation app would receive: per junction, the color each approach
// sees, how long it has been shown and the earliest time it can change. The online demo has no
// API server, so there it shows the same fields from the recorded frames.
import { $, h } from './dom.js';

const ENDPOINT = '/api/v1/spat';

export class SpatPanel {
  constructor(ctx) {
    this.ctx = ctx;
    this.card = $('#spat-panel');
    this.timer = null;
    this.visible = true;
    this.time = h('span', {});
    this.message = h('div', { class: 'act-note' }, 'waiting for the simulation…');
    this.table = h('table', {});
    this.pre = h('pre', {});
    this.details = h('details', {}, h('summary', { class: 'act-note' }, 'raw JSON (what an app downloads)'), this.pre);
    const link = ctx.static
      ? h('span', { class: 'act-note', title: 'The API answers while the live twin runs (python -m teamb twin)' }, 'from the recording')
      : h('a', { href: ENDPOINT, target: '_blank', rel: 'noopener' }, 'open ↗');
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
      if (!this.live) this.render(null, s.state === 'loading' ? 'Starting the simulation…' : 'No simulation running.');
    });
    this.render(null, 'waiting for the simulation…');
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
        if (r.status === 503) this.render(null, 'No simulation running.');
        else if (!r.ok) this.render(null, `The API answered ${r.status}.`);
        else this.render(await r.json());
      } catch {
        this.render(null, 'Server not reachable.');
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
    this.table.append(h('tr', {}, h('th', {}, ''), h('th', {}, 'approach colors'), h('th', {}, 'state'), h('th', {}, 'shown'), h('th', { title: 'When the current state is expected to end (the API also gives min/max)' }, 'changes in'), h('th', {}, '')));
    for (const [j, s] of Object.entries(data.junctions || {})) {
      const colors = s.colors || {};
      // Newer API versions predict the end of the state (state_ends_in_s: {min, max, likely}).
      const ends = s.state_ends_in_s || {};
      const changes = typeof ends.likely === 'number' ? `~${Math.round(ends.likely)} s` : `≥ ${Math.ceil(s.min_time_to_change ?? 0)} s`;
      const range = typeof ends.min === 'number' ? `min ${Math.round(ends.min)} s${typeof ends.max === 'number' ? `, max ${Math.round(ends.max)} s` : ''}` : '';
      this.table.append(
        h('tr', {},
          h('td', {}, h('b', {}, j)),
          h('td', {}, ...['W', 'E', 'N', 'S'].map((a) => h('span', { title: `${a} approach: ${colors[a]}` }, h('span', { class: `lamp ${colors[a] || 'R'}` }), a, ' '))),
          h('td', {}, s.signal),
          h('td', {}, `${Math.round(s.time_in_state ?? 0)} s`),
          h('td', { title: range }, changes),
          h('td', {}, s.preempted_by ? h('span', { class: 'badge red' }, `EV ${s.preempted_by}`) : '')),
      );
    }
    if (this.details.open) this.pre.textContent = JSON.stringify(data, null, 1);
  }
}
