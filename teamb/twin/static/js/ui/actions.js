// Actions panel: dispatch an emergency vehicle, close/reopen a road (also by clicking a road in
// the 3D view), start/stop the fake navigation-data attack. Every action is a SimEnv command
// sent over the WebSocket (see "Commands" in docs/ARCHITECTURE.md).
import { fmtClock, vehicleLabel } from '../util.js';
import { $, fillSelect, h, toast } from './dom.js';

export class ActionsPanel {
  constructor(ctx) {
    this.ctx = ctx;
    this.closures = [];
    this.attack = null;
    const { meta } = ctx;
    const root = $('#actions');

    // --- emergency vehicle
    this.evKind = h('select', { title: 'Vehicle type' });
    fillSelect(this.evKind, meta.ev_kinds.map((k) => ({ value: k.id, label: k.label })));
    this.evRoute = h('select', { title: 'Route' });
    fillSelect(this.evRoute, meta.emergency_routes.map((r) => ({ value: r.id, label: r.label })));
    this.evFollow = h('input', { type: 'checkbox', checked: true });
    const dispatch = h('button', { class: 'btn small bad', onclick: () => this.dispatch() }, 'Dispatch');
    root.append(
      h('div', { class: 'act' },
        h('div', { class: 'act-title' }, h('span', { class: 'sw round', style: { background: '#ff4d4d' } }), 'Emergency vehicle'),
        h('div', { class: 'act-row' }, this.evKind, this.evRoute),
        h('div', { class: 'act-row' }, h('label', { class: 'act-check' }, this.evFollow, 'follow with the camera'), h('span', { style: { flex: 1 } }), dispatch),
      ),
    );

    // --- road closure
    this.edge = h('select', { title: 'Road (edge)' });
    fillSelect(this.edge, meta.closable_edges.map((e) => ({ value: e.id, label: e.label })), 'J2_J3');
    this.cause = h('select', { title: 'Cause' });
    fillSelect(this.cause, meta.closure_causes.map((c) => ({ value: c.id, label: c.label })));
    this.closedList = h('div', { class: 'act-list' });
    this.bothDirs = h('input', { type: 'checkbox' });
    root.append(
      h('div', { class: 'act' },
        h('div', { class: 'act-title' }, h('span', { class: 'sw', style: { background: '#3b82c4' } }), 'Road closure (disaster)'),
        h('div', { class: 'act-row' }, this.edge),
        h('div', { class: 'act-row' }, this.cause,
          h('button', { class: 'btn small warn', onclick: () => this.closeRoad(this.edge.value, this.cause.value, this.bothDirs.checked) }, 'Close'),
          h('button', { class: 'btn small', onclick: () => this.reopenRoad(this.edge.value, this.bothDirs.checked) }, 'Reopen')),
        h('div', { class: 'act-row' }, h('label', { class: 'act-check' }, this.bothDirs, 'both directions')),
        this.closedList,
        h('div', { class: 'act-note' }, 'Tip: click any road in the 3D view to close or reopen it.'),
      ),
    );

    // --- fake-data attack
    this.target = h('select', { title: 'Where the phantom phones claim a queue' });
    fillSelect(this.target, meta.attack_targets.map((t) => ({ value: `${t.junction}:${t.approach}`, label: t.label })));
    this.phones = h('input', { type: 'number', min: 1, max: 500, value: 99, title: 'Number of phantom phones' });
    this.attackStatus = h('div', { class: 'act-note' }, 'Like the 2020 Berlin "99 phones" stunt: phones report a jam that is not there.');
    root.append(
      h('div', { class: 'act' },
        h('div', { class: 'act-title' }, h('span', { class: 'sw', style: { background: '#a855f7' } }), 'Fake navigation data'),
        h('div', { class: 'act-row' }, this.target, this.phones),
        h('div', { class: 'act-row' },
          h('button', { class: 'btn small purple', onclick: () => this.startAttack() }, 'Start attack'),
          h('button', { class: 'btn small', onclick: () => this.stopAttack() }, 'Stop')),
        this.attackStatus,
      ),
    );

    this.menu = $('#road-menu');
    document.addEventListener('pointerdown', (e) => {
      if (!this.menu.hidden && !this.menu.contains(e.target)) this.menu.hidden = true;
    });
    ctx.bus.on('frame', (f) => this.onFrame(f));
    ctx.bus.on('road-click', ({ edge, x, y }) => this.showRoadMenu(edge, x, y));
  }

  async send(command, okText) {
    const r = await this.ctx.socket.command(command);
    if (r.ok === false) toast(r.error || 'command failed', 'error', 6000);
    else if (okText) toast(typeof okText === 'function' ? okText(r) : okText, 'ok');
    return r;
  }

  async dispatch() {
    const route = this.ctx.meta.emergency_routes.find((r) => r.id === this.evRoute.value);
    if (!route) return;
    const r = await this.send(
      { type: 'dispatch_ev', origin: route.origin, destination: route.destination, kind: this.evKind.value },
      (reply) => `${vehicleLabel(reply.result) || 'Vehicle'} dispatched: ${route.label}`,
    );
    if (r.ok !== false && r.result && this.evFollow.checked) this.ctx.camera.followVehicle(r.result);
  }

  closeRoad(edge, cause, bothDirections = false) {
    const what = bothDirections ? `${edge} (both directions)` : edge;
    return this.send({ type: 'close_road', edge, cause, both_directions: bothDirections }, (r) => {
      const res = r.result || {};
      return `Road ${what} closed (${cause})${res.rerouted != null ? ` · ${res.rerouted} vehicles rerouted` : ''}`;
    });
  }

  reopenRoad(edge, bothDirections = false) {
    return this.send({ type: 'reopen_road', edge, both_directions: bothDirections }, `Road ${edge}${bothDirections ? ' (both directions)' : ''} reopened`);
  }

  startAttack() {
    const [junction, approach] = this.target.value.split(':');
    const n = Math.max(1, Math.min(500, Number(this.phones.value) || 99));
    return this.send({ type: 'start_attack', junction, approach, n }, `Fake-data attack started: ${n} phantom phones at ${junction} ${approach}`);
  }

  stopAttack() {
    return this.send({ type: 'stop_attack' }, 'Fake-data attack stopped');
  }

  onFrame(f) {
    const closures = f.closures || [];
    const key = closures.map((c) => c.edge).join(',');
    if (key !== this._closureKey) {
      this._closureKey = key;
      this.closures = closures;
      this.closedList.innerHTML = '';
      for (const c of closures) {
        const detour = Array.isArray(c.detour) && c.detour.length ? ` Detour: ${c.detour.join(' → ')}.` : '';
        this.closedList.append(
          h('button', { class: 'btn small', title: `Closed at ${fmtClock(c.since)} (${c.cause}).${detour} Click to reopen.`, onclick: () => this.reopenRoad(c.edge) }, `${c.edge} · reopen`),
        );
      }
    }
    const a = f.attack;
    const alerts = (f.alerts || []).filter((x) => x.type === 'probe_detector_mismatch');
    if (a) {
      this.attackStatus.innerHTML = '';
      this.attackStatus.append(
        h('span', { class: 'badge purple' }, 'attack running'),
        ` ${a.n} phones at ${a.junction} ${a.approach} since ${fmtClock(a.since)} · `,
        alerts.length ? h('span', { class: 'badge green' }, 'cross-check caught it') : h('span', { class: 'badge yellow' }, 'not flagged yet'),
      );
    } else if (this.attack) {
      this.attackStatus.textContent = 'No attack running.';
    }
    this.attack = a;
  }

  showRoadMenu(edgeId, x, y) {
    const { meta } = this.ctx;
    const edge = meta.closable_edges.find((e) => e.id === edgeId);
    const closed = this.closures.find((c) => c.edge === edgeId);
    const m = this.menu;
    m.innerHTML = '';
    m.append(h('div', { class: 'pt' }, edge ? edge.label : edgeId));
    if (!edge) {
      m.append(h('div', { class: 'ps' }, 'This is an entry/exit road at the edge of the network. Closing it would block traffic from entering, so it is not offered.'));
    } else if (closed) {
      m.append(
        h('div', { class: 'ps' }, `Closed since ${fmtClock(closed.since)} (${closed.cause}).`),
        h('div', { class: 'row' }, h('button', { class: 'btn small good', onclick: () => { this.reopenRoad(edgeId); m.hidden = true; } }, 'Reopen road')),
      );
    } else {
      const cause = h('select');
      fillSelect(cause, meta.closure_causes.map((c) => ({ value: c.id, label: c.label })));
      const both = h('input', { type: 'checkbox' });
      m.append(
        h('div', { class: 'ps' }, 'Close this road? Vehicles that planned to use it are rerouted.'),
        h('div', { class: 'row' }, cause, h('button', { class: 'btn small warn', onclick: () => { this.closeRoad(edgeId, cause.value, both.checked); m.hidden = true; } }, 'Close road')),
        h('label', { class: 'act-check' }, both, 'both directions'),
      );
    }
    m.hidden = false;
    const host = m.parentElement.getBoundingClientRect();
    const w = m.offsetWidth;
    const hh = m.offsetHeight;
    m.style.left = `${Math.min(Math.max(8, x - host.left + 12), host.width - w - 8)}px`;
    m.style.top = `${Math.min(Math.max(8, y - host.top + 12), host.height - hh - 8)}px`;
  }
}
