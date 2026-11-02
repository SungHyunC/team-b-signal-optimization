// Event log: everything SimEnv.log_event() reports (frame.events), newest first.
// Add a line to STYLE to give a new event type its own color and wording.
import { fmtClock, vehicleLabel, APPROACH_NAMES } from '../util.js';
import { $, h } from './dom.js';

const pct = (v) => (v == null ? '?' : `${Math.round(v * 100)}%`);
const AXIS = { EW: 'east–west', NS: 'north–south' };

export const STYLE = {
  started: ['#3aa0ff', (e) => `Run started · ${e.scenario} · ${e.controller} · seed ${e.seed} · coverage ${pct(e.coverage)}`],
  ev_dispatched: ['#ff4d4d', (e) => `${vehicleLabel(e.vehicle)} dispatched (${e.origin} → ${e.destination})`],
  ev_arrived: ['#22c55e', (e) => `${vehicleLabel(e.vehicle)} reached its destination`],
  preemption: ['#ff7a45', (e) => `Green for ${vehicleLabel(e.vehicle)} at ${e.junction} (${AXIS[e.axis] || e.axis}${e.distance != null ? `, ${e.distance} m out` : ''})`],
  road_closed: ['#fb923c', (e) => `Road ${e.edge} closed (${e.cause || 'closure'})${e.rerouted != null ? ` · ${e.rerouted} vehicles rerouted` : ''}${e.unavoidable ? ` · ${e.unavoidable} stuck` : ''}`],
  event_failed: ['#ef4444', (e) => `Scheduled event failed: ${e.kind}${e.error ? ` (${e.error})` : ''}`],
  road_reopened: ['#22c55e', (e) => `Road ${e.edge} reopened`],
  attack_started: ['#a855f7', (e) => `Fake-data attack: ${e.n} phantom phones at ${e.junction} ${APPROACH_NAMES[e.approach] || e.approach} approach`],
  attack_stopped: ['#c4a5ff', () => 'Fake-data attack stopped'],
  recommendation_ready: ['#3aa0ff', (e) => `AI recommendation ready${e.improvement_pct != null ? ` (expected ${Number(e.improvement_pct).toFixed(1)}% less delay)` : ''}`],
  recommendation_approved: ['#22c55e', () => 'AI recommendation approved and applied'],
  recommendation_rejected: ['#8b9ab3', () => 'AI recommendation rejected'],
  recommendation_failed: ['#ef4444', (e) => `AI search failed: ${e.error || 'unknown error'}`],
  plan_applied: ['#22c55e', (e) => `New signal plan applied${e.plan && e.plan.cycle ? ` (cycle ${Math.round(e.plan.cycle)} s)` : ''}`],
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
    this.root.append(h('li', { class: 'empty' }, 'No events yet. Scenario events and your actions show up here.'));
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
    this.count.textContent = `${this.n} event${this.n === 1 ? '' : 's'}`;
  }
}
