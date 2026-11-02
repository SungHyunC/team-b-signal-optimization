// Results tab: experiment reports from GET /api/results (results/experiments/*/report.json,
// written by teamb.experiments). Grouped bar charts with 95 % confidence intervals, drawn as
// plain SVG, plus every other table-shaped section of the report. Every field is optional:
// whatever a report contains is shown, and the report's own "definitions" explain the metrics.
import { fmtNum } from './util.js';
import { $, h } from './ui/dom.js';

const METRICS = [
  { key: 'mean_delay_s', label: 'Mean delay', unit: 's / veh', digits: 1, better: 'lower' },
  // Positive = less delay than the baseline (paired over seeds), see report.definitions.
  { key: 'delta_vs_baseline_pct', label: 'Delay reduction vs baseline', unit: '%', digits: 1, better: 'higher', signed: true },
  { key: 'p95_travel_time_s', label: '95th pct travel time', unit: 's', digits: 0, better: 'lower' },
  { key: 'stops_per_veh', label: 'Stops per vehicle', unit: '', digits: 2, better: 'lower' },
  { key: 'unfinished_pct', label: 'Unfinished trips', unit: '%', digits: 1, better: 'lower' },
  { key: 'ev_mean_travel_time_s', label: 'Emergency vehicle travel time', unit: 's', digits: 0, better: 'lower' },
];
const SECTION_TITLES = {
  coverage_sweep: 'Coverage sweep (is navigation data enough?)',
  estimation: 'Probe estimation error',
  security: 'Fake-data attack (security test)',
  recovery: 'Recovery after the disruption',
  emergency: 'Emergency vehicles',
  perf01: 'Unfinished trips (PERF-01)',
  failed_runs: 'Failed runs',
};
const PALETTE = ['#8b9ab3', '#3aa0ff', '#22c55e', '#fbbf24', '#a855f7', '#fb923c', '#ef4444', '#14b8a6', '#f472b6'];

/** {mean, ci95} | number | null -> {mean, ci} | null */
function stat(v) {
  if (typeof v === 'number' && isFinite(v)) return { mean: v, ci: null };
  if (v && typeof v === 'object' && typeof v.mean === 'number' && isFinite(v.mean)) return { mean: v.mean, ci: typeof v.ci95 === 'number' && isFinite(v.ci95) ? v.ci95 : null };
  return null;
}

function fmtStat(v, digits = 2, signed = false) {
  const s = stat(v);
  if (!s) return v === null || v === undefined || (typeof v === 'object' && !Array.isArray(v)) ? '–' : String(v);
  return `${signed && s.mean > 0 ? '+' : ''}${fmtNum(s.mean, digits)}${s.ci != null ? ` ± ${fmtNum(s.ci, digits)}` : ''}`;
}

function niceTicks(lo, hi, n = 5) {
  const span = hi - lo || 1;
  const step0 = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
  const ticks = [];
  for (let v = Math.floor(lo / step) * step; v <= hi + step * 0.001; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

const svgEl = (tag, attrs = {}, text) => {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text != null) el.textContent = text;
  return el;
};

export class ResultsView {
  constructor(ctx) {
    this.ctx = ctx;
    this.root = $('#results');
    this.reports = [];
    this.selected = 0;
    this.metric = 'mean_delay_s';
  }

  async show() {
    this.root.innerHTML = '';
    this.root.append(h('div', { class: 'empty-state' }, 'Loading experiment reports…'));
    try {
      this.reports = await this.ctx.api.get('/api/results');
    } catch (err) {
      this.root.innerHTML = '';
      this.root.append(h('div', { class: 'empty-state' }, `Could not load reports: ${err.message}`));
      return;
    }
    // Show real experiments before scratch ones (names starting with "_").
    this.reports.sort((a, b) => String(a.name).startsWith('_') - String(b.name).startsWith('_'));
    this.selected = Math.min(this.selected, Math.max(0, this.reports.length - 1));
    this.render();
  }

  render() {
    const root = this.root;
    root.innerHTML = '';
    const refresh = h('button', { class: 'btn', onclick: () => this.show() }, 'Refresh');
    if (!this.reports.length) {
      root.append(
        h('div', { class: 'res-head' }, h('h1', {}, 'Experiment results'), h('div', { class: 'grow' }), refresh),
        h('div', { class: 'empty-state' },
          h('div', {}, 'No experiment reports yet.'),
          h('div', {}, 'Batch experiments write results/experiments/<name>/report.json; they appear here automatically.'),
          h('code', {}, 'python -m teamb.experiments --help')),
      );
      return;
    }
    const report = this.reports[this.selected];
    const select = h('select', {});
    this.reports.forEach((r, i) => select.append(h('option', { value: i }, `${r.name}${r.created ? ` · ${r.created}` : ''}`)));
    select.value = this.selected;
    select.addEventListener('change', () => {
      this.selected = Number(select.value);
      this.render();
    });
    root.append(h('div', { class: 'res-head' }, h('h1', {}, 'Experiment results'), select, h('div', { class: 'grow' }), refresh));

    const rows = Array.isArray(report.rows) ? report.rows : [];
    const defs = report.definitions && typeof report.definitions === 'object' ? report.definitions : {};
    const metrics = METRICS.filter((m) => rows.some((r) => stat(r[m.key])));
    if (!metrics.some((m) => m.key === this.metric) && metrics.length) this.metric = metrics[0].key;
    const metric = METRICS.find((m) => m.key === this.metric);
    const baseline = report.baseline || 'fixed_time';
    const tabs = h('div', { class: 'metric-tabs' });
    for (const m of metrics) {
      const b = h('button', { class: m.key === this.metric ? 'active' : '', title: defs[m.key] || '' }, m.label);
      b.addEventListener('click', () => {
        this.metric = m.key;
        this.render();
      });
      tabs.append(b);
    }
    const seeds = [...new Set(rows.map((r) => r.n_seeds).filter((n) => n != null))];
    root.append(
      h('div', { class: 'res-card' },
        h('h2', {}, metric ? `${metric.label}${metric.unit ? ` (${metric.unit})` : ''}` : 'No numeric results'),
        h('div', { class: 'sub' },
          `${rows.length} rows · baseline: ${baseline}${seeds.length ? ` · ${seeds.join('/')} seeds` : ''} · bars: mean over seeds, whiskers: 95% confidence interval${metric ? ` · ${metric.better} is better` : ''}`),
        metric && defs[metric.key] ? h('div', { class: 'sub' }, defs[metric.key]) : '',
        tabs,
        h('div', { class: 'res-chart' }, metric ? this.chart(rows, metric, baseline) : ''),
      ),
      this.table(rows, metrics, baseline),
    );
    for (const [key, value] of Object.entries(report)) {
      if (key === 'rows' || !Array.isArray(value) || !value.length || typeof value[0] !== 'object') continue;
      root.append(this.section(SECTION_TITLES[key] || key.replace(/_/g, ' '), value, defs));
    }
    root.append(this.info(report));
  }

  chart(rows, metric, baseline) {
    // Groups: scenario (+ coverage when it varies); bars: controllers.
    const coverages = new Set(rows.map((r) => r.coverage));
    const groupKey = (r) => `${r.scenario ?? 'all'}${coverages.size > 1 && r.coverage != null ? ` · ${Math.round(r.coverage * 100)}%` : ''}`;
    const groups = [...new Set(rows.map(groupKey))];
    const controllers = [...new Set(rows.map((r) => r.controller ?? '?'))].sort((a, b) => (a === baseline ? -1 : b === baseline ? 1 : 0));
    const color = (c) => (c === baseline ? PALETTE[0] : PALETTE[1 + ((controllers.indexOf(c) - 1 + PALETTE.length - 1) % (PALETTE.length - 1))]);
    const values = [];
    for (const r of rows) {
      const s = stat(r[metric.key]);
      if (s) values.push(s.mean - (s.ci || 0), s.mean + (s.ci || 0));
    }
    let lo = Math.min(0, ...values);
    let hi = Math.max(0, ...values);
    if (hi === lo) hi = lo + 1;
    const ticks = niceTicks(lo, hi);
    lo = Math.min(lo, ticks[0]);
    hi = Math.max(hi, ticks[ticks.length - 1]);
    const W = 1160;
    const H = 400;
    const m = { l: 64, r: 16, t: 34, b: 58 };
    const iw = W - m.l - m.r;
    const ih = H - m.t - m.b;
    const y = (v) => m.t + ih - ((v - lo) / (hi - lo)) * ih;
    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': metric.label });
    for (const t of ticks) {
      svg.append(svgEl('line', { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), stroke: t === 0 ? '#5d6c88' : '#1d2a42', 'stroke-width': t === 0 ? 1.5 : 1 }));
      svg.append(svgEl('text', { x: m.l - 8, y: y(t) + 4, 'text-anchor': 'end', fill: '#8b9ab3', 'font-size': 12 }, fmtNum(t, Math.abs(hi - lo) < 5 ? 1 : 0)));
    }
    const gw = iw / Math.max(1, groups.length);
    const bw = Math.min(56, (gw * 0.78) / Math.max(1, controllers.length));
    groups.forEach((g, gi) => {
      const gx = m.l + gi * gw + gw / 2;
      svg.append(svgEl('text', { x: gx, y: H - m.b + 22, 'text-anchor': 'middle', fill: '#dce5f3', 'font-size': 13, 'font-weight': 600 }, g));
      controllers.forEach((c, ci) => {
        const row = rows.find((r) => groupKey(r) === g && (r.controller ?? '?') === c);
        const s = row && stat(row[metric.key]);
        if (!s) return;
        const x = gx - (controllers.length * bw) / 2 + ci * bw;
        const y0 = y(0); // bars grow from zero (the axis always includes it)
        const y1 = y(s.mean);
        const rect = svgEl('rect', { x: x + 3, y: Math.min(y0, y1), width: bw - 6, height: Math.max(1, Math.abs(y1 - y0)), rx: 3, fill: color(c), opacity: c === baseline ? 0.75 : 0.95 });
        rect.append(svgEl('title', {}, `${c} · ${g}: ${fmtStat(row[metric.key], metric.digits, metric.signed)}${row.n_seeds ? ` (${row.n_seeds} seeds)` : ''}${row.p_value != null ? ` · p = ${fmtNum(row.p_value, 3)}` : ''}`));
        svg.append(rect);
        if (s.ci != null) {
          const cx = x + bw / 2;
          const ya = y(s.mean - s.ci);
          const yb = y(s.mean + s.ci);
          svg.append(svgEl('line', { x1: cx, x2: cx, y1: ya, y2: yb, stroke: '#dce5f3', 'stroke-width': 1.5 }));
          for (const yy of [ya, yb]) svg.append(svgEl('line', { x1: cx - 5, x2: cx + 5, y1: yy, y2: yy, stroke: '#dce5f3', 'stroke-width': 1.5 }));
        }
        const labelY = s.mean >= 0 ? Math.min(y1, s.ci != null ? y(s.mean + s.ci) : y1) - 6 : Math.max(y1, s.ci != null ? y(s.mean - s.ci) : y1) + 14;
        svg.append(svgEl('text', { x: x + bw / 2, y: labelY, 'text-anchor': 'middle', fill: '#c6d1e3', 'font-size': 11 }, `${metric.signed && s.mean > 0 ? '+' : ''}${fmtNum(s.mean, metric.digits)}`));
      });
    });
    let lx = m.l;
    for (const c of controllers) {
      svg.append(svgEl('rect', { x: lx, y: 10, width: 12, height: 12, rx: 2, fill: color(c) }));
      const label = `${c}${c === baseline ? ' (baseline)' : ''}`;
      svg.append(svgEl('text', { x: lx + 17, y: 20, fill: '#c6d1e3', 'font-size': 12 }, label));
      lx += 30 + label.length * 7;
    }
    return svg;
  }

  table(rows, metrics, baseline) {
    const hasP = rows.some((r) => typeof r.p_value === 'number');
    const head = h('tr', {},
      h('th', {}, 'Scenario'), h('th', {}, 'Controller'), h('th', {}, 'Coverage'), h('th', {}, 'Seeds'),
      ...metrics.map((m) => h('th', {}, `${m.label}${m.unit ? ` (${m.unit})` : ''}`)),
      hasP ? h('th', { title: 'Two-sided paired t-test vs the baseline' }, 'p-value') : '');
    const body = rows.map((r) => {
      const isBase = r.controller === baseline || r.is_baseline === true;
      return h('tr', { class: isBase ? 'baseline' : '' },
        h('td', {}, r.scenario ?? '–'),
        h('td', {}, `${r.controller ?? '–'}${isBase ? ' (baseline)' : ''}`),
        h('td', {}, r.coverage != null ? `${Math.round(r.coverage * 100)}%` : '–'),
        h('td', {}, r.n_seeds ?? '–'),
        ...metrics.map((m) => {
          const s = stat(r[m.key]);
          if (!s) return h('td', {}, '–');
          const cls = m.key === 'delta_vs_baseline_pct' && !isBase ? (s.mean > 0 ? 'better' : s.mean < 0 ? 'worse' : '') : '';
          return h('td', { class: cls }, fmtStat(r[m.key], m.digits, m.signed));
        }),
        hasP ? h('td', {}, typeof r.p_value === 'number' ? fmtNum(r.p_value, 3) : '–') : '');
    });
    return h('div', { class: 'res-card' }, h('h2', {}, 'All rows'), h('div', { style: { overflow: 'auto' } }, h('table', { class: 'res-table' }, head, ...body)));
  }

  /** Any other list-of-objects section of the report, as a table of its scalar columns. */
  section(title, items, defs) {
    const cols = [];
    for (const item of items) {
      for (const [k, v] of Object.entries(item)) {
        const scalar = v === null || ['number', 'string', 'boolean'].includes(typeof v) || stat(v) || (v && typeof v === 'object' && 'mean' in v);
        if (scalar && !cols.includes(k)) cols.push(k);
      }
    }
    const show = cols.slice(0, 14);
    const table = h('table', { class: 'res-table' },
      h('tr', {}, ...show.map((c) => h('th', { title: defs[c] || '' }, c.replace(/_/g, ' ')))),
      ...items.map((item) => h('tr', {}, ...show.map((c) => h('td', {}, fmtStat(item[c], 2))))));
    return h('details', { class: 'res-card' }, h('summary', { style: { cursor: 'pointer', fontWeight: 700 } }, `${title} · ${items.length} row${items.length === 1 ? '' : 's'}`), h('div', { style: { overflow: 'auto', marginTop: '8px' } }, table));
  }

  info(report) {
    const chips = [];
    for (const k of ['created', 'code_revision', 'sumo_version']) if (report[k]) chips.push(`${k.replace(/_/g, ' ')}: ${report[k]}`);
    const c = report.compute || {};
    if (c.runs_ok != null) chips.push(`runs: ${c.runs_ok} ok${c.runs_failed ? `, ${c.runs_failed} failed` : ''}`);
    if (c.experiment_wall_time_s != null) chips.push(`wall time: ${fmtNum(c.experiment_wall_time_s / 60, 1)} min`);
    if (c.sim_speedup != null) chips.push(`${fmtNum(c.sim_speedup, 0)}× faster than real time`);
    const commands = Array.isArray(report.commands) ? report.commands : [];
    return h('div', { class: 'res-card' },
      h('h2', {}, 'Report info'),
      h('div', { class: 'chips' }, ...chips.map((x) => h('span', { class: 'chip' }, x))),
      commands.length ? h('div', { class: 'sub', style: { marginTop: '10px' } }, 'Reproduce with:') : '',
      ...commands.map((cmd) => h('pre', { class: 'spat', style: { margin: '4px 0 0', whiteSpace: 'pre-wrap', fontSize: '12px', background: '#070c16', padding: '8px', borderRadius: '6px' } }, cmd)));
  }
}
