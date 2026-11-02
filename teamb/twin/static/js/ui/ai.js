// AI recommendation card: "AI recommends -> engineer approves" (Google Green Light style).
// Shown while the controller implements pending_recommendation() (e.g. ai_recommender) and
// fed from frame.recommendation:
//   {id, status: searching|pending|approved|rejected, created_t, plan: {cycle, splits, offsets},
//    current_plan, expected: {mean_delay_s, baseline_mean_delay_s, improvement_pct},
//    based_on: {coverage, window_s, trials, estimated_flows}, progress: {done, total}}
// Buttons send {type: 'approve'|'reject', id} and {type: 'optimize'} to the controller.
import { fmtClock, fmtNum } from '../util.js';
import { $, h, toast } from './dom.js';

const num = (v) => (typeof v === 'number' && isFinite(v) ? v : null);

function flattenFlows(flows, prefix = '') {
  // estimated_flows can be {name: vph} or nested {J1: {W: vph}}: show it as chips either way.
  const out = [];
  if (!flows || typeof flows !== 'object') return out;
  for (const [k, v] of Object.entries(flows)) {
    if (v && typeof v === 'object') out.push(...flattenFlows(v, `${prefix}${k} `));
    else out.push([`${prefix}${k}`, v]);
  }
  return out;
}

export class AiCard {
  constructor(ctx) {
    this.ctx = ctx;
    this.root = $('#ai-card');
    this.recommends = new Set(ctx.meta.controllers.filter((c) => c.recommends).map((c) => c.name));
    this.controller = null;
    this.lastId = null;
    this.lastKey = null;
    this.collapsed = false;
    this.busy = false;
    ctx.bus.on('frame', (f) => this.update(f));
    ctx.bus.on('session', () => {
      this.lastId = null;
      this.lastKey = null;
      this.root.hidden = true;
    });
  }

  update(frame) {
    this.controller = frame.controller;
    const rec = frame.recommendation;
    const active = this.recommends.has(frame.controller) || !!rec;
    if (!active) {
      this.root.hidden = true;
      return;
    }
    this.root.hidden = false;
    const idStatus = rec ? `${rec.id}:${rec.status}` : null;
    if (idStatus !== this.lastId) {
      this.lastId = idStatus;
      if (rec && rec.status === 'pending') {
        // A plan is waiting for a human decision: make sure the card is open and say so.
        this.collapsed = false;
        toast('AI recommendation ready: review it and approve or reject.', 'ok', 6000);
      }
    }
    const key = JSON.stringify(rec) + this.collapsed + this.busy;
    if (key === this.lastKey) return; // avoid rebuilding the DOM 12 times a second
    this.lastKey = key;
    this.render(rec, frame.t);
  }

  render(rec, t) {
    const status = rec ? rec.status : 'collecting';
    const badge = {
      searching: ['blue', 'searching'],
      pending: ['yellow', 'needs approval'],
      approved: ['green', 'applied'],
      rejected: ['purple', 'rejected'],
      collecting: ['blue', 'collecting data'],
    }[status] || ['blue', status];
    const root = this.root;
    root.className = `ai-card ${status}${this.collapsed ? ' collapsed' : ''}`;
    root.innerHTML = '';
    const head = h('div', { class: 'ai-head', title: 'Click to collapse / expand' },
      h('div', { class: 'ai-icon' }, 'AI'),
      h('div', {}, h('div', { class: 'ai-title' }, 'AI timing recommendation'), h('div', { class: 'ai-sub' }, 'AI recommends · traffic engineer approves')),
      h('span', { class: `badge ${badge[0]}` }, badge[1]),
    );
    head.addEventListener('click', () => {
      this.collapsed = !this.collapsed;
      this.lastKey = null;
      this.render(rec, t);
    });
    root.append(head);
    const body = h('div', { class: 'ai-body' });
    root.append(body);

    if (!rec) {
      body.append(
        h('div', { class: 'ai-note' }, 'The recommender is learning demand from navigation-app data. It proposes a new signal plan when it finds a better one; nothing changes until someone approves it.'),
        h('div', { class: 'ai-actions' }, this.button('Optimize now', 'primary', { type: 'optimize' })),
      );
      return;
    }

    if (status === 'searching') {
      const p = rec.progress || {};
      const done = num(p.done) ?? 0;
      const total = num(p.total) ?? 0;
      body.append(
        h('div', { class: 'ai-note' }, `Searching signal plans in a fast model of the corridor${total ? ` · ${done}/${total} trials` : '…'}`),
        h('div', { class: 'progress' }, h('i', { style: { width: `${total ? (100 * done) / total : 15}%` } })),
      );
    }

    const exp = rec.expected || {};
    const imp = num(exp.improvement_pct);
    if (imp != null || num(exp.mean_delay_s) != null) {
      body.append(
        h('div', { class: 'ai-big' },
          h('div', { class: `num${imp != null && imp < 0 ? ' neg' : ''}` }, imp != null ? `${imp > 0 ? '−' : '+'}${fmtNum(Math.abs(imp), 1)}%` : '–'),
          h('div', { class: 'desc' }, 'expected change in mean delay', h('br'),
            `${fmtNum(num(exp.baseline_mean_delay_s), 1)} s → ${fmtNum(num(exp.mean_delay_s), 1)} s per vehicle`)),
      );
    }

    if (rec.plan) body.append(this.planTable(rec.plan, rec.current_plan));

    const based = rec.based_on || {};
    const chips = [];
    if (based.source) chips.push(based.source);
    if (num(based.coverage) != null) chips.push(`coverage ${Math.round(based.coverage * 100)}%`);
    if (num(based.window_s) != null) chips.push(`last ${fmtClock(based.window_s)} of data`);
    if (num(based.probe_samples) != null) chips.push(`${fmtNum(based.probe_samples, 0)} probe samples`);
    if (num(based.trials) != null) chips.push(`${based.trials} trials`);
    if (num(based.ignored_untrusted) != null && based.ignored_untrusted > 0) chips.push(`${based.ignored_untrusted} untrusted reports ignored`);
    if (rec.created_t != null) chips.push(`started at ${fmtClock(rec.created_t)}`);
    if (chips.length) body.append(h('div', { class: 'ai-note' }, 'Based on'), h('div', { class: 'chips' }, ...chips.map((c) => h('span', { class: 'chip' }, c))));
    const flows = based.estimated_flows;
    if (flows && typeof flows === 'object') {
      const nestedFlows = Object.values(flows).every((v) => v && typeof v === 'object');
      body.append(h('div', { class: 'ai-note' }, 'Estimated demand (veh/h) from navigation-app data'));
      if (nestedFlows) body.append(this.flowTable(flows));
      else body.append(h('div', { class: 'chips' }, ...flattenFlows(flows).slice(0, 16).map(([k, v]) => h('span', { class: 'chip' }, `${k}: ${typeof v === 'number' ? fmtNum(v, 0) : v}`))));
    }
    if (rec.note) body.append(h('div', { class: 'ai-note' }, rec.note));
    if (rec.error) body.append(h('div', { class: 'ai-note', style: { color: '#ff9a9a' } }, `Search failed: ${rec.error}`));
    if ((status === 'approved' || status === 'rejected') && rec.decided_by) {
      body.append(h('div', { class: 'ai-note' }, `${status === 'approved' ? 'Approved' : 'Rejected'} by ${rec.decided_by}${rec.decided_t != null ? ` at ${fmtClock(rec.decided_t)}` : ''}.`));
    }

    if (status === 'pending') {
      body.append(
        h('div', { class: 'ai-actions' }, this.button('Approve & apply', 'good', { type: 'approve', id: rec.id }), this.button('Reject', 'bad', { type: 'reject', id: rec.id })),
        h('div', { class: 'ai-note' }, 'The safety supervisor still enforces minimum green, yellow and all-red after approval.'),
      );
    } else if (status === 'approved' || status === 'rejected') {
      body.append(h('div', { class: 'ai-actions' }, this.button('Optimize again', '', { type: 'optimize' })));
    }
  }

  flowTable(flows) {
    const sides = ['W', 'E', 'N', 'S'].filter((s) => Object.values(flows).some((f) => f[s] != null));
    const rows = Object.keys(flows).sort().map((j) =>
      h('tr', {}, h('td', {}, j), ...sides.map((s) => h('td', {}, typeof flows[j][s] === 'number' ? fmtNum(flows[j][s], 0) : '–'))));
    return h('table', { class: 'ai-table' }, h('tr', {}, h('th', {}, ''), ...sides.map((s) => h('th', {}, `from ${s}`))), ...rows);
  }

  planTable(plan, current) {
    const cur = current || {};
    const js = [...new Set([...Object.keys(plan.splits || {}), ...Object.keys(plan.offsets || {})])].sort();
    const fmtPct = (v) => (num(v) != null ? `${Math.round(v * 100)}%` : '–');
    const fmtS = (v) => (num(v) != null ? `${fmtNum(v, 0)} s` : '–');
    const cell = (newV, oldV, f) => {
      const changed = num(oldV) != null && num(newV) != null && Math.abs(newV - oldV) > 1e-6;
      return h('td', { class: changed ? 'chg' : '' }, num(oldV) != null && changed ? `${f(oldV)} → ${f(newV)}` : f(newV));
    };
    const rows = js.map((j) => {
      const share = (plan.splits || {})[j];
      return h('tr', {},
        h('td', {}, j),
        h('td', {}, h('span', { class: 'splitbar', title: 'E–W share of the green time' }, h('i', { style: { width: `${Math.round((num(share) ?? 0.5) * 100)}%` } }))),
        cell(share, (cur.splits || {})[j], fmtPct),
        cell((plan.offsets || {})[j], (cur.offsets || {})[j], fmtS));
    });
    const cycle = num(plan.cycle);
    const oldCycle = num(cur.cycle);
    return h('div', {},
      h('div', { class: 'ai-note' }, `Cycle ${cycle != null ? `${fmtNum(cycle, 0)} s` : '–'}${oldCycle != null && cycle != null && oldCycle !== cycle ? ` (now ${fmtNum(oldCycle, 0)} s)` : ''}`),
      h('table', { class: 'ai-table' }, h('tr', {}, h('th', {}, ''), h('th', {}, 'E–W green'), h('th', {}, 'share'), h('th', {}, 'offset')), ...rows));
  }

  button(label, kind, command) {
    const b = h('button', { class: `btn ${kind}`, disabled: this.busy || null }, label);
    b.addEventListener('click', async (e) => {
      e.stopPropagation();
      this.busy = true;
      this.lastKey = null;
      const r = await this.ctx.socket.command(command);
      this.busy = false;
      this.lastKey = null;
      if (r.ok === false) toast(r.error || 'the controller did not accept the command', r.demo ? 'info' : 'error', 6000);
      else toast(command.type === 'approve' ? 'Plan approved: the new timing is being applied.' : command.type === 'reject' ? 'Plan rejected: keeping the current timing.' : 'Optimization started.', 'ok');
    });
    return b;
  }
}
