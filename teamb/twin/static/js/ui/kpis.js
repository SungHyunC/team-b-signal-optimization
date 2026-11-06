// Live KPI tiles with sparklines, from frame.kpi (sampled by the metrics collector every 5 sim-s).
import { addKo, t } from '../i18n.js';
import { fmtNum } from '../util.js';
import { $, h } from './dom.js';

addKo({
  'Mean delay': '평균 지연',
  'cars on the road now: {s} s lost so far': '운행 중인 차량: 지금까지 {s} s 지연',
  'Average time lost per finished trip (last 300 trips), compared with free-flow driving':
    '완료된 통행 1건당 평균 손실 시간 (최근 300건, 막힘 없이 달릴 때와 비교)',
  'Vehicles in the network': '구간 내 차량',
  'Halting (queued)': '정지 차량 (대기열)',
  spillback: '대기열 역류',
  '{pct}% of vehicles stopped': '차량의 {pct}% 정지',
  'Mean speed': '평균 속도',
  'Trips completed': '완료된 통행',
  'throughput ≈ {n} veh/h (last 5 min)': '처리량 ≈ {n} veh/h (최근 5분)',
  'throughput ≈ {n} veh/h (last {m} min)': '처리량 ≈ {n} veh/h (최근 {m}분)',
  'throughput ≈ {n} veh/h (last {s} s)': '처리량 ≈ {n} veh/h (최근 {s}초)',
  'throughput: collecting…': '처리량: 집계 중…',
  'sampled every 5 s': '5초마다 집계',
});

const HISTORY = 240; // samples kept per sparkline (20 min of sim time)

/** Throughput from the arrived counter over the last ~5 minutes of sim time:
 *  {rate (veh/h), window (s)}, where the window is shorter early in a run. null below 30 s. */
export function throughput(history) {
  if (history.length < 2) return null;
  const last = history[history.length - 1];
  let first = history[0];
  for (let i = history.length - 1; i >= 0; i--) {
    if (last.t - history[i].t >= 300) {
      first = history[i];
      break;
    }
  }
  const dt = last.t - first.t;
  return dt > 30 ? { rate: ((last.arrived - first.arrived) * 3600) / dt, window: dt } : null;
}

/** The tile text: says which window the rate covers (samples every 5 s: 5 min = 295-300 s). */
export function throughputText(tp) {
  if (!tp) return t('throughput: collecting…');
  const n = fmtNum(tp.rate, 0);
  if (tp.window >= 295) return t('throughput ≈ {n} veh/h (last 5 min)', { n });
  if (tp.window >= 120) return t('throughput ≈ {n} veh/h (last {m} min)', { n, m: Math.round(tp.window / 60) });
  return t('throughput ≈ {n} veh/h (last {s} s)', { n, s: Math.round(tp.window) });
}

// label and title are translated when the tiles are built; sub and badge when they render.
const TILES = [
  {
    id: 'delay', label: 'Mean delay', unit: 's / veh', color: '#3aa0ff',
    value: (k) => k.mean_delay, digits: 1,
    sub: (k) => t('cars on the road now: {s} s lost so far', { s: fmtNum(k.current_mean_delay, 1) }),
    title: 'Average time lost per finished trip (last 300 trips), compared with free-flow driving',
  },
  { id: 'vehicles', label: 'Vehicles in the network', unit: '', color: '#a3b6d6', value: (k) => k.vehicles, digits: 0 },
  {
    id: 'halting', label: 'Halting (queued)', unit: 'veh', color: '#fb923c', value: (k) => k.halting, digits: 0,
    badge: (k) => (k.spillback ? ['red', t('spillback')] : null),
    sub: (k) => (k.vehicles ? t('{pct}% of vehicles stopped', { pct: Math.round((100 * k.halting) / k.vehicles) }) : ''),
  },
  {
    id: 'speed', label: 'Mean speed', unit: 'km/h', color: '#22c55e', value: (k) => (k.mean_speed != null ? k.mean_speed * 3.6 : null), digits: 0,
    sub: (k) => (k.mean_speed != null ? `${fmtNum(k.mean_speed * 2.23694, 0)} mph` : ''),
  },
  {
    id: 'arrived', label: 'Trips completed', unit: '', color: '#c084fc', value: (k) => k.arrived, digits: 0,
    sub: (k, hist) => throughputText(throughput(hist)),
  },
];

export class KpiPanel {
  constructor(ctx) {
    this.root = $('#kpis');
    this.history = [];
    this.lastT = null;
    this.tiles = TILES.map((def) => {
      const value = h('div', { class: 'kpi-value' }, '–');
      const sub = h('div', { class: 'kpi-sub' });
      const canvas = h('canvas', { width: 208, height: 68 });
      const label = h('div', { class: 'kpi-label' }, t(def.label));
      const el = h('div', { class: 'kpi', title: def.title ? t(def.title) : null }, h('div', {}, label, value, sub), canvas);
      this.root.append(el);
      return { def, el, value, sub, canvas, label };
    });
    ctx.bus.on('hello', (msg) => {
      this.history = (msg.kpi_history || []).slice(-HISTORY);
      this.lastT = this.history.length ? this.history[this.history.length - 1].t : null;
      this.render(this.history[this.history.length - 1]);
    });
    ctx.bus.on('session', () => {
      this.history = [];
      this.lastT = null;
      this.render(null);
    });
    ctx.bus.on('frame', (f) => {
      const k = f.kpi;
      if (!k || k.t == null) return;
      if (k.t !== this.lastT) {
        this.lastT = k.t;
        this.history.push(k);
        if (this.history.length > HISTORY) this.history.shift();
      }
      this.render(k);
    });
    $('#kpi-hint').textContent = t('sampled every 5 s');
  }

  render(k) {
    for (const tile of this.tiles) {
      if (!k) {
        tile.value.textContent = '–';
        tile.sub.textContent = '';
        this.spark(tile, []);
        continue;
      }
      const v = tile.def.value(k);
      tile.value.innerHTML = '';
      tile.value.append(fmtNum(v, tile.def.digits));
      if (tile.def.unit) tile.value.append(h('small', {}, tile.def.unit));
      const badge = tile.def.badge && tile.def.badge(k);
      if (badge) tile.value.append(' ', h('span', { class: `badge ${badge[0]}` }, badge[1]));
      tile.sub.textContent = tile.def.sub ? tile.def.sub(k, this.history) : '';
      this.spark(tile, this.history.map((s) => tile.def.value(s)).filter((x) => x != null && isFinite(x)));
    }
  }

  spark(tile, values) {
    const c = tile.canvas;
    const g = c.getContext('2d');
    const W = c.width;
    const H = c.height;
    g.clearRect(0, 0, W, H);
    if (values.length < 2) return;
    const max = Math.max(...values);
    const min = Math.min(0, ...values);
    const span = max - min || 1;
    const pad = 6;
    const x = (i) => pad + ((W - 2 * pad) * i) / (values.length - 1);
    const y = (v) => H - pad - ((H - 2 * pad) * (v - min)) / span;
    g.beginPath();
    values.forEach((v, i) => (i ? g.lineTo(x(i), y(v)) : g.moveTo(x(i), y(v))));
    g.strokeStyle = tile.def.color;
    g.lineWidth = 3;
    g.lineJoin = 'round';
    g.stroke();
    g.lineTo(x(values.length - 1), H - pad);
    g.lineTo(x(0), H - pad);
    g.closePath();
    const grad = g.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, `${tile.def.color}55`);
    grad.addColorStop(1, `${tile.def.color}00`);
    g.fillStyle = grad;
    g.fill();
    const lx = x(values.length - 1);
    const ly = y(values[values.length - 1]);
    g.beginPath();
    g.arc(lx, ly, 4, 0, Math.PI * 2);
    g.fillStyle = tile.def.color;
    g.fill();
  }
}
