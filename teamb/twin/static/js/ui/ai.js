// AI recommendation card: "AI recommends -> engineer approves" (Google Green Light style).
// Shown while the controller implements pending_recommendation() (e.g. ai_recommender) and
// fed from frame.recommendation:
//   {id, status: searching|pending|approved|rejected, created_t, plan: {cycle, splits, offsets},
//    current_plan, expected: {mean_delay_s, baseline_mean_delay_s, improvement_pct},
//    based_on: {coverage, window_s, trials, estimated_flows}, progress: {done, total}}
// Buttons send {type: 'approve'|'reject', id} and {type: 'optimize'} to the controller.
import { addKo, t } from '../i18n.js';
import { fmtClock, fmtNum } from '../util.js';
import { $, h, toast } from './dom.js';

addKo({
  'AI recommendation ready: review it and approve or reject.': 'AI 추천이 나왔어요. 검토하고 승인하거나 거절하세요.',
  searching: '탐색 중',
  'needs approval': '승인 필요',
  applied: '적용됨',
  rejected: '거절됨',
  'collecting data': '데이터 수집 중',
  'Click to collapse / expand': '클릭하면 접거나 펼쳐요',
  'AI timing recommendation': 'AI 신호 계획 추천',
  'AI recommends · traffic engineer approves': 'AI가 추천 · 교통 엔지니어가 승인',
  'The recommender is learning demand from navigation-app data. It proposes a new signal plan when it finds a better one; nothing changes until someone approves it.':
    '추천 AI가 내비 앱 데이터로 교통 수요를 학습하고 있어요. 더 나은 신호 계획을 찾으면 제안하고, 누군가 승인하기 전에는 아무것도 바뀌지 않아요.',
  'Optimize now': '지금 최적화',
  'Searching signal plans in a fast model of the corridor': '빠른 구간 모델에서 신호 계획을 탐색하는 중',
  '{done}/{total} trials': '{done}/{total}회 시도',
  'expected change in mean delay': '평균 지연 예상 변화',
  '{from} s → {to} s per vehicle': '차량당 {from} s → {to} s',
  'navigation-app probes only': '내비 앱 데이터만',
  'coverage {pct}%': '내비 데이터 비율 {pct}%',
  'last {time} of data': '최근 {time} 데이터',
  '{n} probe samples': '내비 데이터 표본 {n}개',
  '{n} trials': '시도 {n}회',
  '{n} untrusted reports ignored': '믿을 수 없는 보고 {n}건 무시',
  'started at {time}': '{time}에 시작',
  'Based on': '추천 근거',
  'Estimated demand (veh/h) from navigation-app data': '내비 앱 데이터로 추정한 교통 수요 (veh/h)',
  'no candidate beat the current plan; keep it': '지금 신호 계획보다 나은 후보가 없어서 그대로 유지해요',
  '(from cache)': '(캐시된 결과)',
  'Search failed: {error}': '탐색에 실패했어요: {error}',
  engineer: '엔지니어',
  system: '시스템',
  auto_approve: '자동 승인',
  'Approved by {who} at {time}.': '{time}에 승인됐어요 ({who}).',
  'Approved by {who}.': '승인됐어요 ({who}).',
  'Rejected by {who} at {time}.': '{time}에 거절됐어요 ({who}).',
  'Rejected by {who}.': '거절됐어요 ({who}).',
  'Approve & apply': '승인 및 적용',
  Reject: '거절',
  'The safety supervisor still enforces minimum green, yellow and all-red after approval.':
    '승인한 뒤에도 안전 감독기가 최소 녹색·황색·전적색 시간을 지켜요.',
  'Optimize again': '다시 최적화',
  'from W': '서쪽에서',
  'from E': '동쪽에서',
  'from N': '북쪽에서',
  'from S': '남쪽에서',
  'E–W share of the green time': '녹색 시간 중 동서 방향 비율',
  'Cycle {cycle}': '주기 {cycle}',
  '(now {s} s)': '(현재 {s} s)',
  'E–W green': '동서 녹색',
  share: '비율',
  offset: '오프셋',
  'the controller did not accept the command': '신호 제어 방식이 명령을 받아들이지 않았어요',
  'a search is already running': '이미 탐색 중이에요',
  'no recommendation is waiting for approval': '승인을 기다리는 추천이 없어요',
  'no simulation running': '실행 중인 시뮬레이션이 없어요',
  'Plan approved: the new timing is being applied.': '신호 계획을 승인했어요. 새 신호 시간을 적용하는 중이에요.',
  'Plan rejected: keeping the current timing.': '신호 계획을 거절했어요. 지금 신호 시간을 유지해요.',
  'Optimization started.': '최적화를 시작했어요.',
});

const num = (v) => (typeof v === 'number' && isFinite(v) ? v : null);

// rec.note is server text: translate the phrases it is made of and keep anything else as sent.
const NOTE_PHRASES = ['no candidate beat the current plan; keep it', '(from cache)'];
const noteText = (note) => NOTE_PHRASES.reduce((s, p) => s.replace(p, () => t(p)), String(note));

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
        toast(t('AI recommendation ready: review it and approve or reject.'), 'ok', 6000);
      }
    }
    const key = JSON.stringify(rec) + this.collapsed + this.busy;
    if (key === this.lastKey) return; // avoid rebuilding the DOM 12 times a second
    this.lastKey = key;
    this.render(rec, frame.t);
  }

  render(rec, time) {
    const status = rec ? rec.status : 'collecting';
    const badge = {
      searching: ['blue', t('searching')],
      pending: ['yellow', t('needs approval')],
      approved: ['green', t('applied')],
      rejected: ['purple', t('rejected')],
      collecting: ['blue', t('collecting data')],
    }[status] || ['blue', status];
    const root = this.root;
    root.className = `ai-card ${status}${this.collapsed ? ' collapsed' : ''}`;
    root.innerHTML = '';
    const head = h('div', { class: 'ai-head', title: t('Click to collapse / expand') },
      h('div', { class: 'ai-icon' }, 'AI'),
      h('div', {}, h('div', { class: 'ai-title' }, t('AI timing recommendation')), h('div', { class: 'ai-sub' }, t('AI recommends · traffic engineer approves'))),
      h('span', { class: `badge ${badge[0]}` }, badge[1]),
    );
    head.addEventListener('click', () => {
      this.collapsed = !this.collapsed;
      this.lastKey = null;
      this.render(rec, time);
    });
    root.append(head);
    const body = h('div', { class: 'ai-body' });
    root.append(body);

    if (!rec) {
      body.append(
        h('div', { class: 'ai-note' }, t('The recommender is learning demand from navigation-app data. It proposes a new signal plan when it finds a better one; nothing changes until someone approves it.')),
        h('div', { class: 'ai-actions' }, this.button(t('Optimize now'), 'primary', { type: 'optimize' })),
      );
      return;
    }

    if (status === 'searching') {
      const p = rec.progress || {};
      const done = num(p.done) ?? 0;
      const total = num(p.total) ?? 0;
      body.append(
        h('div', { class: 'ai-note' }, `${t('Searching signal plans in a fast model of the corridor')}${total ? ` · ${t('{done}/{total} trials', { done, total })}` : '…'}`),
        h('div', { class: 'progress' }, h('i', { style: { width: `${total ? (100 * done) / total : 15}%` } })),
      );
    }

    const exp = rec.expected || {};
    const imp = num(exp.improvement_pct);
    if (imp != null || num(exp.mean_delay_s) != null) {
      body.append(
        h('div', { class: 'ai-big' },
          h('div', { class: `num${imp != null && imp < 0 ? ' neg' : ''}` }, imp != null ? `${imp > 0 ? '−' : '+'}${fmtNum(Math.abs(imp), 1)}%` : '–'),
          h('div', { class: 'desc' }, t('expected change in mean delay'), h('br'),
            t('{from} s → {to} s per vehicle', { from: fmtNum(num(exp.baseline_mean_delay_s), 1), to: fmtNum(num(exp.mean_delay_s), 1) }))),
      );
    }

    if (rec.plan) body.append(this.planTable(rec.plan, rec.current_plan));

    const based = rec.based_on || {};
    const chips = [];
    if (based.source) chips.push(t(based.source));
    if (num(based.coverage) != null) chips.push(t('coverage {pct}%', { pct: Math.round(based.coverage * 100) }));
    if (num(based.window_s) != null) chips.push(t('last {time} of data', { time: fmtClock(based.window_s) }));
    if (num(based.probe_samples) != null) chips.push(t('{n} probe samples', { n: fmtNum(based.probe_samples, 0) }));
    if (num(based.trials) != null) chips.push(t('{n} trials', { n: based.trials }));
    if (num(based.ignored_untrusted) != null && based.ignored_untrusted > 0) chips.push(t('{n} untrusted reports ignored', { n: based.ignored_untrusted }));
    if (rec.created_t != null) chips.push(t('started at {time}', { time: fmtClock(rec.created_t) }));
    if (chips.length) body.append(h('div', { class: 'ai-note' }, t('Based on')), h('div', { class: 'chips' }, ...chips.map((c) => h('span', { class: 'chip' }, c))));
    const flows = based.estimated_flows;
    if (flows && typeof flows === 'object') {
      const nestedFlows = Object.values(flows).every((v) => v && typeof v === 'object');
      body.append(h('div', { class: 'ai-note' }, t('Estimated demand (veh/h) from navigation-app data')));
      if (nestedFlows) body.append(this.flowTable(flows));
      else body.append(h('div', { class: 'chips' }, ...flattenFlows(flows).slice(0, 16).map(([k, v]) => h('span', { class: 'chip' }, `${k}: ${typeof v === 'number' ? fmtNum(v, 0) : v}`))));
    }
    if (rec.note) body.append(h('div', { class: 'ai-note' }, noteText(rec.note)));
    if (rec.error) body.append(h('div', { class: 'ai-note', style: { color: '#ff9a9a' } }, t('Search failed: {error}', { error: rec.error })));
    if ((status === 'approved' || status === 'rejected') && rec.decided_by) {
      const vars = { who: t(rec.decided_by), time: fmtClock(rec.decided_t) };
      const at = rec.decided_t != null;
      const text = status === 'approved'
        ? (at ? t('Approved by {who} at {time}.', vars) : t('Approved by {who}.', vars))
        : (at ? t('Rejected by {who} at {time}.', vars) : t('Rejected by {who}.', vars));
      body.append(h('div', { class: 'ai-note' }, text));
    }

    if (status === 'pending') {
      body.append(
        h('div', { class: 'ai-actions' }, this.button(t('Approve & apply'), 'good', { type: 'approve', id: rec.id }), this.button(t('Reject'), 'bad', { type: 'reject', id: rec.id })),
        h('div', { class: 'ai-note' }, t('The safety supervisor still enforces minimum green, yellow and all-red after approval.')),
      );
    } else if (status === 'approved' || status === 'rejected') {
      body.append(h('div', { class: 'ai-actions' }, this.button(t('Optimize again'), '', { type: 'optimize' })));
    }
  }

  flowTable(flows) {
    const sides = ['W', 'E', 'N', 'S'].filter((s) => Object.values(flows).some((f) => f[s] != null));
    const rows = Object.keys(flows).sort().map((j) =>
      h('tr', {}, h('td', {}, j), ...sides.map((s) => h('td', {}, typeof flows[j][s] === 'number' ? fmtNum(flows[j][s], 0) : '–'))));
    return h('table', { class: 'ai-table' }, h('tr', {}, h('th', {}, ''), ...sides.map((s) => h('th', {}, t(`from ${s}`)))), ...rows);
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
        h('td', {}, h('span', { class: 'splitbar', title: t('E–W share of the green time') }, h('i', { style: { width: `${Math.round((num(share) ?? 0.5) * 100)}%` } }))),
        cell(share, (cur.splits || {})[j], fmtPct),
        cell((plan.offsets || {})[j], (cur.offsets || {})[j], fmtS));
    });
    const cycle = num(plan.cycle);
    const oldCycle = num(cur.cycle);
    const cycleText = t('Cycle {cycle}', { cycle: cycle != null ? `${fmtNum(cycle, 0)} s` : '–' });
    const nowText = oldCycle != null && cycle != null && oldCycle !== cycle ? ` ${t('(now {s} s)', { s: fmtNum(oldCycle, 0) })}` : '';
    return h('div', {},
      h('div', { class: 'ai-note' }, `${cycleText}${nowText}`),
      h('table', { class: 'ai-table' }, h('tr', {}, h('th', {}, ''), h('th', {}, t('E–W green')), h('th', {}, t('share')), h('th', {}, t('offset'))), ...rows));
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
      if (r.ok === false) toast(t(r.error || 'the controller did not accept the command'), r.demo ? 'info' : 'error', 6000);
      else toast(command.type === 'approve' ? t('Plan approved: the new timing is being applied.') : command.type === 'reject' ? t('Plan rejected: keeping the current timing.') : t('Optimization started.'), 'ok');
    });
    return b;
  }
}
