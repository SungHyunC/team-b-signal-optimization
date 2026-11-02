// Live KPI tiles with sparklines, from frame.kpi (sampled by the metrics collector every 5 sim-s).
import { fmtNum } from '../util.js';
import { $, h } from './dom.js';

const HISTORY = 240; // samples kept per sparkline (20 min of sim time)

/** Throughput (veh/h) from the arrived counter over the last ~5 minutes of sim time. */
function throughput(history) {
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
  return dt > 30 ? ((last.arrived - first.arrived) * 3600) / dt : null;
}

const TILES = [
  {
    id: 'delay', label: 'Mean delay', unit: 's / veh', color: '#3aa0ff',
    value: (k) => k.mean_delay, digits: 1,
    sub: (k) => `cars on the road now: ${fmtNum(k.current_mean_delay, 1)} s lost so far`,
    title: 'Average time lost per finished trip (last 300 trips), compared with free-flow driving',
  },
  { id: 'vehicles', label: 'Vehicles in the network', unit: '', color: '#a3b6d6', value: (k) => k.vehicles, digits: 0 },
  {
    id: 'halting', label: 'Halting (queued)', unit: 'veh', color: '#fb923c', value: (k) => k.halting, digits: 0,
    badge: (k) => (k.spillback ? ['red', 'spillback'] : null),
    sub: (k) => (k.vehicles ? `${Math.round((100 * k.halting) / k.vehicles)}% of vehicles stopped` : ''),
  },
  {
    id: 'speed', label: 'Mean speed', unit: 'km/h', color: '#22c55e', value: (k) => (k.mean_speed != null ? k.mean_speed * 3.6 : null), digits: 0,
    sub: (k) => (k.mean_speed != null ? `${fmtNum(k.mean_speed * 2.23694, 0)} mph` : ''),
  },
  {
    id: 'arrived', label: 'Trips completed', unit: '', color: '#c084fc', value: (k) => k.arrived, digits: 0,
    sub: (k, hist) => {
      const tp = throughput(hist);
      return tp != null ? `throughput ≈ ${fmtNum(tp, 0)} veh/h (last 5 min)` : 'throughput: collecting…';
    },
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
      const label = h('div', { class: 'kpi-label' }, def.label);
      const el = h('div', { class: 'kpi', title: def.title || null }, h('div', {}, label, value, sub), canvas);
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
    $('#kpi-hint').textContent = 'sampled every 5 s';
  }

  render(k) {
    for (const t of this.tiles) {
      if (!k) {
        t.value.textContent = '–';
        t.sub.textContent = '';
        this.spark(t, []);
        continue;
      }
      const v = t.def.value(k);
      t.value.innerHTML = '';
      t.value.append(fmtNum(v, t.def.digits));
      if (t.def.unit) t.value.append(h('small', {}, t.def.unit));
      const badge = t.def.badge && t.def.badge(k);
      if (badge) t.value.append(' ', h('span', { class: `badge ${badge[0]}` }, badge[1]));
      t.sub.textContent = t.def.sub ? t.def.sub(k, this.history) : '';
      this.spark(t, this.history.map((s) => t.def.value(s)).filter((x) => x != null && isFinite(x)));
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
