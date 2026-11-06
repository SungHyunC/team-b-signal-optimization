// Results tab: experiment reports from GET /api/results (results/experiments/*/report.json,
// written by teamb.experiments). Grouped bar charts with 95 % confidence intervals, drawn as
// plain SVG, plus every other table-shaped section of the report. Every field is optional:
// whatever a report contains is shown, and the report's own "definitions" explain the metrics.
// In Korean, the report's English definitions and column names are looked up by metric id
// (DEFINITIONS_KO, COLUMNS_KO); a metric missing there stays in English.
import { fmtNum } from './util.js';
import { $, h } from './ui/dom.js';
import { addKo, controllerLabel, lang, scenarioTitle, t } from './i18n.js';

addKo({
  // metrics
  'Mean delay': '평균 지연',
  'Delay reduction vs baseline': '기준 대비 지연 감소',
  '95th pct travel time': '95백분위 통행 시간',
  'Stops per vehicle': '차량당 정지 횟수',
  'Unfinished trips': '미완료 통행',
  'Emergency vehicle travel time': '긴급차량 통행 시간',
  // report sections
  'Coverage sweep (is navigation data enough?)': '내비 데이터 비율별 결과 (내비 데이터만으로 충분할까요?)',
  'Probe estimation error': '내비 데이터 추정 오차',
  'Fake-data attack (security test)': '가짜 데이터 공격 (보안 테스트)',
  'Recovery after the disruption': '돌발 상황 이후 회복',
  'Emergency vehicles': '긴급차량',
  'Unfinished trips (PERF-01)': '미완료 통행 (PERF-01)',
  'Failed runs': '실패한 실행',
  // page, empty and error states
  'Loading experiment reports…': '실험 보고서를 불러오는 중…',
  'Could not load reports: {error}': '보고서를 불러오지 못했어요: {error}',
  Refresh: '새로고침',
  'Experiment results': '실험 결과',
  'No experiment reports yet.': '아직 실험 보고서가 없어요.',
  'Batch experiments write results/experiments/<name>/report.json; they appear here automatically.':
    '일괄 실험이 results/experiments/<name>/report.json을 만들면 여기에 자동으로 나타나요.',
  'No numeric results': '수치 결과 없음',
  '{n} rows': '{n}개 행',
  '{n} row': '{n}개 행',
  'baseline: {controller}': '기준: {controller}',
  '{seeds} seeds': '시드 {seeds}개',
  'bars: mean over seeds, whiskers: 95% confidence interval': '막대: 시드 평균, 오차 막대: 95% 신뢰구간',
  'lower is better': '낮을수록 좋음',
  'higher is better': '높을수록 좋음',
  // chart
  all: '전체',
  '({n} seeds)': '(시드 {n}개)',
  '{controller} (baseline)': '{controller} (기준)',
  // tables
  Scenario: '시나리오',
  Controller: '신호 제어 방식',
  Coverage: '내비 데이터 비율',
  Seeds: '시드 수',
  'Two-sided paired t-test vs the baseline': '기준과 비교한 양측 대응 t-검정',
  'p-value': 'p값',
  'All rows': '전체 결과',
  true: '예',
  false: '아니요',
  // report info
  'created: {value}': '생성 시각: {value}',
  'code revision: {value}': '코드 버전: {value}',
  'sumo version: {value}': 'SUMO 버전: {value}',
  'runs: {ok} ok': '실행: 성공 {ok}회',
  'runs: {ok} ok, {failed} failed': '실행: 성공 {ok}회, 실패 {failed}회',
  'wall time: {min} min': '총 소요 시간: {min} min',
  '{speedup}× faster than real time': '실제 시간보다 {speedup}배 빠름',
  'Report info': '보고서 정보',
  'Reproduce with:': '재현 명령:',
});

const METRICS = [
  { key: 'mean_delay_s', label: t('Mean delay'), unit: 's / veh', digits: 1, better: 'lower' },
  // Positive = less delay than the baseline (paired over seeds), see report.definitions.
  { key: 'delta_vs_baseline_pct', label: t('Delay reduction vs baseline'), unit: '%', digits: 1, better: 'higher', signed: true },
  { key: 'p95_travel_time_s', label: t('95th pct travel time'), unit: 's', digits: 0, better: 'lower' },
  { key: 'stops_per_veh', label: t('Stops per vehicle'), unit: '', digits: 2, better: 'lower' },
  { key: 'unfinished_pct', label: t('Unfinished trips'), unit: '%', digits: 1, better: 'lower' },
  { key: 'ev_mean_travel_time_s', label: t('Emergency vehicle travel time'), unit: 's', digits: 0, better: 'lower' },
];
const SECTION_TITLES = {
  coverage_sweep: t('Coverage sweep (is navigation data enough?)'),
  estimation: t('Probe estimation error'),
  security: t('Fake-data attack (security test)'),
  recovery: t('Recovery after the disruption'),
  emergency: t('Emergency vehicles'),
  perf01: t('Unfinished trips (PERF-01)'),
  failed_runs: t('Failed runs'),
};
const PALETTE = ['#8b9ab3', '#3aa0ff', '#22c55e', '#fbbf24', '#a855f7', '#fb923c', '#ef4444', '#14b8a6', '#f472b6'];

// Korean for report.definitions (teamb/experiments/analysis.py DEFINITIONS), by metric id.
const DEFINITIONS_KO = {
  mean_delay_s: '워밍업이 끝난 뒤 실행 종료 전까지([warmup, end)) 출발해 도착한 통행의 SUMO timeLoss 평균이에요 (s/veh, 주요 평가 지표).',
  ci95: '시드 간 95% t 신뢰구간의 반폭이에요 (평균 ± ci95). 시드가 하나면 null이에요.',
  delta_vs_baseline_pct:
    '같은 시드끼리 짝지어 비교한 기준 대비 평균 지연 개선율이에요. 시드마다 100 × (기준 − 비교 대상) / 기준을 구해 평균을 내요. 양수면 기준보다 좋아요 (지연이 적어요).',
  mean_delay_diff_s: '같은 시드끼리 짝지은 평균 지연 차이(비교 대상 − 기준, s/veh)예요. 음수면 더 좋아요.',
  p_value: '시드별 지연 차이에 대한 양측 대응 t-검정이에요.',
  p_holm: '같은 시나리오의 비교 대상끼리 Holm–Bonferroni 보정을 한 p_value예요.',
  unfinished_pct: '100 × (종료 시점에 아직 도로망에 있는 통행 + 끝내 진입하지 못한 통행) / (완료 + 미완료) (PERF-01).',
  ev_mean_travel_time_s: '도착한 긴급차량의 평균 통행 시간이에요.',
  baseline_match: "'exact' = 내비 데이터 비율과 샘플링 방식이 같은 기준 실행, 'scenario' = 시나리오만 같고 내비 데이터 비율이 다른 기준 실행.",
};

// Korean column names of the extra report sections (coverage_sweep, estimation, security,
// recovery, emergency, perf01, failed_runs), by column id. English shows the id itself.
const COLUMNS_KO = {
  scenario: '시나리오',
  controller: '신호 제어 방식',
  coverage: '내비 데이터 비율',
  sampling: '샘플링 방식',
  ev_preemption: '긴급차량 우선 신호',
  n_seeds: '시드 수',
  n_runs: '실행 수',
  mean_delay_s: '평균 지연 (s)',
  delta_vs_baseline_pct: '기준 대비 지연 감소 (%)',
  probe_share: '내비 데이터 공유 차량 비율',
  probe_share_arterial: '내비 데이터 공유 차량 비율 (간선도로)',
  probe_share_cross: '내비 데이터 공유 차량 비율 (교차 도로)',
  est_queue_mae: '대기열 추정 오차 (MAE)',
  est_queue_bias: '대기열 추정 편향',
  est_queue_bias_arterial: '대기열 추정 편향 (간선도로)',
  est_queue_bias_cross: '대기열 추정 편향 (교차 도로)',
  est_queue_adj_mae: '보정 대기열 추정 오차 (MAE)',
  est_queue_adj_bias: '보정 대기열 추정 편향',
  det_queue_mae: '루프 감지기 대기열 오차 (MAE)',
  fused_queue_mae: '융합 대기열 오차 (MAE)',
  est_flow_mae: '교통량 추정 오차 (MAE)',
  est_flow_bias: '교통량 추정 편향',
  false_alarm_s: '오경보 시간 (s)',
  detected_share: '공격 탐지 비율',
  detection_delay_s: '탐지 소요 시간 (s)',
  alert_s: '경보 시간 (s)',
  recovery_time_s: '회복 시간 (s)',
  censored: '미회복 실행 수',
  excess_delay_veh_h: '초과 지연 (veh·h)',
  spillback_duration_s: '대기열 역류 시간 (s)',
  ev_count: '긴급차량 수',
  ev_mean_travel_time_s: '긴급차량 평균 통행 시간 (s)',
  ev_mean_delay_s: '긴급차량 평균 지연 (s)',
  others_mean_delay_s: '다른 차량 평균 지연 (s)',
  ev_extra_delay_others_s: '긴급차량 주변 추가 지연 (s)',
  completed: '완료 통행 수',
  unfinished: '미완료 통행 수',
  unfinished_pct: '미완료 통행 비율 (%)',
  in_network_at_end: '종료 시 남은 통행',
  never_inserted: '진입 못 한 통행',
  teleports: '텔레포트 횟수',
  mean_delay_incl_unfinished_s: '미완료 포함 평균 지연 (s)',
  name: '이름',
  error: '오류',
};

/** The report's definition of a metric ('' when it has none), in Korean when we have one. */
function definition(defs, key) {
  if (!defs[key]) return '';
  return (lang === 'ko' && DEFINITIONS_KO[key]) || defs[key];
}

/** Column header of an extra section: the column id ("est queue mae"), or its Korean name. */
function columnLabel(key) {
  return (lang === 'ko' && COLUMNS_KO[key]) || key.replace(/_/g, ' ');
}

// Legend spacing: about 7 px per character at 12 px (as before), 12 px for Hangul/CJK glyphs.
const WIDE = /[\u1100-\u11ff\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]/;
const textWidth = (s) => [...String(s)].reduce((w, ch) => w + (WIDE.test(ch) ? 12 : 7), 0);

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

  /** A controller name from a report: as is in English, its label from ctx.meta in Korean. */
  controllerName(name) {
    if (lang !== 'ko' || name == null) return name;
    const c = (this.ctx.meta?.controllers || []).find((x) => x.name === name);
    return controllerLabel(c || { name });
  }

  /** A scenario name from a report: as is in English, its title from ctx.meta in Korean. */
  scenarioName(name) {
    if (lang !== 'ko' || name == null) return name;
    const s = (this.ctx.meta?.scenarios || []).find((x) => x.name === name);
    return s ? scenarioTitle(s) : name;
  }

  async show() {
    this.root.innerHTML = '';
    this.root.append(h('div', { class: 'empty-state' }, t('Loading experiment reports…')));
    try {
      this.reports = await this.ctx.api.get('/api/results');
    } catch (err) {
      this.root.innerHTML = '';
      this.root.append(h('div', { class: 'empty-state' }, t('Could not load reports: {error}', { error: err.message })));
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
    const refresh = h('button', { class: 'btn', onclick: () => this.show() }, t('Refresh'));
    if (!this.reports.length) {
      root.append(
        h('div', { class: 'res-head' }, h('h1', {}, t('Experiment results')), h('div', { class: 'grow' }), refresh),
        h('div', { class: 'empty-state' },
          h('div', {}, t('No experiment reports yet.')),
          h('div', {}, t('Batch experiments write results/experiments/<name>/report.json; they appear here automatically.')),
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
    root.append(h('div', { class: 'res-head' }, h('h1', {}, t('Experiment results')), select, h('div', { class: 'grow' }), refresh));

    const rows = Array.isArray(report.rows) ? report.rows : [];
    const defs = report.definitions && typeof report.definitions === 'object' ? report.definitions : {};
    const metrics = METRICS.filter((m) => rows.some((r) => stat(r[m.key])));
    if (!metrics.some((m) => m.key === this.metric) && metrics.length) this.metric = metrics[0].key;
    const metric = METRICS.find((m) => m.key === this.metric);
    const baseline = report.baseline || 'fixed_time';
    const tabs = h('div', { class: 'metric-tabs' });
    for (const m of metrics) {
      const b = h('button', { class: m.key === this.metric ? 'active' : '', title: definition(defs, m.key) }, m.label);
      b.addEventListener('click', () => {
        this.metric = m.key;
        this.render();
      });
      tabs.append(b);
    }
    const seeds = [...new Set(rows.map((r) => r.n_seeds).filter((n) => n != null))];
    const summary = [
      t('{n} rows', { n: rows.length }),
      t('baseline: {controller}', { controller: this.controllerName(baseline) }),
      ...(seeds.length ? [t('{seeds} seeds', { seeds: seeds.join('/') })] : []),
      t('bars: mean over seeds, whiskers: 95% confidence interval'),
      ...(metric ? [metric.better === 'higher' ? t('higher is better') : t('lower is better')] : []),
    ];
    root.append(
      h('div', { class: 'res-card' },
        h('h2', {}, metric ? `${metric.label}${metric.unit ? ` (${metric.unit})` : ''}` : t('No numeric results')),
        h('div', { class: 'sub' }, summary.join(' · ')),
        metric && defs[metric.key] ? h('div', { class: 'sub' }, definition(defs, metric.key)) : '',
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
    const covSuffix = (r) => (coverages.size > 1 && r.coverage != null ? ` · ${Math.round(r.coverage * 100)}%` : '');
    const groupKey = (r) => `${r.scenario ?? 'all'}${covSuffix(r)}`;
    // What a group is called on screen: the key in English, the scenario's title in Korean.
    const groupName = new Map(rows.map((r) => [groupKey(r), `${r.scenario != null ? this.scenarioName(r.scenario) : t('all')}${covSuffix(r)}`]));
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
    for (const tick of ticks) {
      svg.append(svgEl('line', { x1: m.l, x2: W - m.r, y1: y(tick), y2: y(tick), stroke: tick === 0 ? '#5d6c88' : '#1d2a42', 'stroke-width': tick === 0 ? 1.5 : 1 }));
      svg.append(svgEl('text', { x: m.l - 8, y: y(tick) + 4, 'text-anchor': 'end', fill: '#8b9ab3', 'font-size': 12 }, fmtNum(tick, Math.abs(hi - lo) < 5 ? 1 : 0)));
    }
    const gw = iw / Math.max(1, groups.length);
    const bw = Math.min(56, (gw * 0.78) / Math.max(1, controllers.length));
    groups.forEach((g, gi) => {
      const gx = m.l + gi * gw + gw / 2;
      svg.append(svgEl('text', { x: gx, y: H - m.b + 22, 'text-anchor': 'middle', fill: '#dce5f3', 'font-size': 13, 'font-weight': 600 }, groupName.get(g)));
      controllers.forEach((c, ci) => {
        const row = rows.find((r) => groupKey(r) === g && (r.controller ?? '?') === c);
        const s = row && stat(row[metric.key]);
        if (!s) return;
        const x = gx - (controllers.length * bw) / 2 + ci * bw;
        const y0 = y(0); // bars grow from zero (the axis always includes it)
        const y1 = y(s.mean);
        const rect = svgEl('rect', { x: x + 3, y: Math.min(y0, y1), width: bw - 6, height: Math.max(1, Math.abs(y1 - y0)), rx: 3, fill: color(c), opacity: c === baseline ? 0.75 : 0.95 });
        const seedsNote = row.n_seeds ? ` ${t('({n} seeds)', { n: row.n_seeds })}` : '';
        rect.append(svgEl('title', {}, `${this.controllerName(c)} · ${groupName.get(g)}: ${fmtStat(row[metric.key], metric.digits, metric.signed)}${seedsNote}${row.p_value != null ? ` · p = ${fmtNum(row.p_value, 3)}` : ''}`));
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
      const label = c === baseline ? t('{controller} (baseline)', { controller: this.controllerName(c) }) : this.controllerName(c);
      svg.append(svgEl('text', { x: lx + 17, y: 20, fill: '#c6d1e3', 'font-size': 12 }, label));
      lx += 30 + textWidth(label);
    }
    return svg;
  }

  table(rows, metrics, baseline) {
    const hasP = rows.some((r) => typeof r.p_value === 'number');
    const head = h('tr', {},
      h('th', {}, t('Scenario')), h('th', {}, t('Controller')), h('th', {}, t('Coverage')), h('th', {}, t('Seeds')),
      ...metrics.map((m) => h('th', {}, `${m.label}${m.unit ? ` (${m.unit})` : ''}`)),
      hasP ? h('th', { title: t('Two-sided paired t-test vs the baseline') }, t('p-value')) : '');
    const body = rows.map((r) => {
      const isBase = r.controller === baseline || r.is_baseline === true;
      const controller = r.controller != null ? this.controllerName(r.controller) : '–';
      return h('tr', { class: isBase ? 'baseline' : '' },
        h('td', {}, r.scenario != null ? this.scenarioName(r.scenario) : '–'),
        h('td', {}, isBase ? t('{controller} (baseline)', { controller }) : controller),
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
    return h('div', { class: 'res-card' }, h('h2', {}, t('All rows')), h('div', { style: { overflow: 'auto' } }, h('table', { class: 'res-table' }, head, ...body)));
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
    const show = cols; // all of them: the card scrolls sideways (e.g. estimation has 17 columns)
    // Scenario / controller names and yes/no in the current language; everything else as before.
    const cell = (c, v) => {
      if (typeof v === 'boolean') return v ? t('true') : t('false');
      if (typeof v === 'string' && c === 'scenario') return this.scenarioName(v);
      if (typeof v === 'string' && c === 'controller') return this.controllerName(v);
      return fmtStat(v, 2);
    };
    const table = h('table', { class: 'res-table' },
      h('tr', {}, ...show.map((c) => h('th', { title: definition(defs, c) }, columnLabel(c)))),
      ...items.map((item) => h('tr', {}, ...show.map((c) => h('td', {}, cell(c, item[c]))))));
    const count = items.length === 1 ? t('{n} row', { n: items.length }) : t('{n} rows', { n: items.length });
    return h('details', { class: 'res-card' }, h('summary', { style: { cursor: 'pointer', fontWeight: 700 } }, `${title} · ${count}`), h('div', { style: { overflow: 'auto', marginTop: '8px' } }, table));
  }

  info(report) {
    const chips = [];
    if (report.created) chips.push(t('created: {value}', { value: report.created }));
    if (report.code_revision) chips.push(t('code revision: {value}', { value: report.code_revision }));
    if (report.sumo_version) chips.push(t('sumo version: {value}', { value: report.sumo_version }));
    const c = report.compute || {};
    if (c.runs_ok != null) {
      chips.push(c.runs_failed ? t('runs: {ok} ok, {failed} failed', { ok: c.runs_ok, failed: c.runs_failed }) : t('runs: {ok} ok', { ok: c.runs_ok }));
    }
    if (c.experiment_wall_time_s != null) chips.push(t('wall time: {min} min', { min: fmtNum(c.experiment_wall_time_s / 60, 1) }));
    if (c.sim_speedup != null) chips.push(t('{speedup}× faster than real time', { speedup: fmtNum(c.sim_speedup, 0) }));
    const commands = Array.isArray(report.commands) ? report.commands : [];
    return h('div', { class: 'res-card' },
      h('h2', {}, t('Report info')),
      h('div', { class: 'chips' }, ...chips.map((x) => h('span', { class: 'chip' }, x))),
      commands.length ? h('div', { class: 'sub', style: { marginTop: '10px' } }, t('Reproduce with:')) : '',
      ...commands.map((cmd) => h('pre', { class: 'spat', style: { margin: '4px 0 0', whiteSpace: 'pre-wrap', fontSize: '12px', background: '#070c16', padding: '8px', borderRadius: '6px' } }, cmd)));
  }
}
