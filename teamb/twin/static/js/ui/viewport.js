// Everything drawn over the 3D view in HTML: title, banners (fake data suspected, attack, EV
// priority, closures, fast-forward), the loading / finished overlay, camera presets with
// "follow emergency vehicle", the legend and the side-panel toggles.
import { fmtClock, fmtNum, vehicleLabel, APPROACH_NAMES } from '../util.js';
import { $, h, toast } from './dom.js';

/** Camera presets and the follow camera. ctx.camera = this. */
export class CameraControl {
  constructor(ctx) {
    this.ctx = ctx;
    this.view = ctx.view;
    this.vehicles = ctx.layers.vehicles;
    this.pending = null; // vehicle id to follow as soon as it appears
    this.autoFollow = false;
    this.bar = $('#camera-bar');
    this.buttons = new Map();
    const add = (key, label, title, fn) => {
      const b = h('button', { title }, label);
      b.addEventListener('click', fn);
      this.bar.append(b);
      this.buttons.set(key, b);
    };
    add('overview', 'Overview', 'Whole corridor (0)', () => this.fly('overview'));
    for (const j of ctx.meta.junctions) add(j, j, `Junction ${j} (${j.slice(1)})`, () => this.fly(j));
    add('top', 'Top', 'Straight down', () => this.fly('top'));
    add('follow', 'Follow EV', 'Chase the newest emergency vehicle (F)', () => this.followLatest());
    const auto = h('input', { type: 'checkbox' });
    auto.addEventListener('change', () => (this.autoFollow = auto.checked));
    this.bar.append(h('label', { title: 'Jump to every newly dispatched emergency vehicle' }, auto, 'auto-follow EVs'));
    this.view.onFollowLost = (byUser) => {
      this.setActive(null);
      if (!byUser) toast('The emergency vehicle left the network; camera released.');
    };
    ctx.bus.on('frame', (f) => {
      if (this.autoFollow) for (const e of f.events || []) if (e.type === 'ev_dispatched') this.pending = { id: e.vehicle, until: performance.now() + 15000 };
      if (this.pending) {
        if (this.vehicles.pose(this.pending.id)) {
          this.follow(this.pending.id);
          this.pending = null;
        } else if (performance.now() > this.pending.until) this.pending = null;
      }
    });
    this.setActive('overview');
  }

  setActive(key) {
    for (const [k, b] of this.buttons) b.classList.toggle('active', k === key);
  }

  fly(name) {
    this.pending = null;
    this.view.flyTo(name);
    this.setActive(name);
  }

  follow(id) {
    this.view.setFollow(() => this.vehicles.pose(id));
    this.setActive('follow');
    toast(`Camera following ${vehicleLabel(id)}. Drag the view to stop.`);
  }

  followVehicle(id) {
    if (this.vehicles.pose(id)) this.follow(id);
    else this.pending = { id, until: performance.now() + 15000 }; // it appears after the next step
  }

  followLatest() {
    const id = this.vehicles.latestEmergency();
    if (id) this.follow(id);
    else toast('No emergency vehicle on the road. Dispatch one under Actions.');
  }
}

export class ViewportChrome {
  constructor(ctx) {
    this.ctx = ctx;
    this.title = $('#vp-title');
    this.banners = $('#banners');
    this.overlay = $('#vp-overlay');
    this.alertUntil = 0;
    this.lastAlert = null;
    this.status = null;
    this.frame = null;
    this.buildLegend();
    const live = $('#live-view');
    $('#toggle-left').addEventListener('click', () => live.classList.toggle('hide-left'));
    $('#toggle-right').addEventListener('click', () => live.classList.toggle('hide-right'));
    ctx.bus.on('status', (s) => {
      this.status = s;
      this.renderOverlay();
      this.renderTitle();
      this.renderBanners();
    });
    ctx.bus.on('frame', (f) => {
      this.frame = f;
      const alerts = (f.alerts || []).filter((a) => a.type === 'probe_detector_mismatch');
      if (alerts.length) {
        this.alertUntil = performance.now() + 4000; // alerts flicker per step: hold the banner a bit
        this.lastAlert = alerts[0];
      }
      this.renderBanners();
    });
    ctx.bus.on('connection', (ok) => {
      this.connected = ok;
      this.renderOverlay();
    });
  }

  hideBootOverlay() {
    this.booted = true;
    this.renderOverlay();
  }

  renderTitle() {
    const s = this.status;
    if (!s || !s.config) {
      this.title.hidden = true;
      return;
    }
    this.title.hidden = false;
    const sc = this.ctx.meta.scenarios.find((x) => x.name === s.config.scenario);
    const ct = this.ctx.meta.controllers.find((x) => x.name === s.config.controller);
    const cov = this.frame && this.frame.coverage != null ? this.frame.coverage : s.config.coverage;
    this.title.innerHTML = '';
    this.title.append(
      h('div', { class: 't1' }, `${sc ? sc.title : s.config.scenario}`),
      h('div', { class: 't2' }, `${ct ? ct.label : s.config.controller} · seed ${s.config.seed}${cov != null ? ` · nav-app coverage ${Math.round(cov * 100)}%` : ''}`),
      s.note ? h('div', { class: 't3' }, s.note) : null, // online demo: what this recording shows
    );
  }

  renderBanners() {
    const f = this.frame;
    const s = this.status;
    const list = [];
    if (s && s.fast_forward_to != null) list.push(['info', `Fast-forwarding to ${fmtClock(s.fast_forward_to)}…`]);
    if (f) {
      if (performance.now() < this.alertUntil && this.lastAlert) {
        const a = this.lastAlert;
        list.push(['alert', `FAKE DATA SUSPECTED at ${a.junction} ${APPROACH_NAMES[a.approach] || a.approach}: navigation apps report ${fmtNum(a.probe_queue, 0)} queued, loop detectors see ${a.detector_queue}`]);
      }
      if (f.attack) list.push(['attack', `Fake-data attack · ${f.attack.n} phantom phones at ${f.attack.junction} ${APPROACH_NAMES[f.attack.approach] || f.attack.approach}`]);
      if ((f.preempting || []).length) list.push(['preempt', `Emergency vehicle priority at ${f.preempting.join(', ')}`]);
      const closed = f.closures || [];
      if (closed.length) list.push(['info', `Road${closed.length > 1 ? 's' : ''} closed: ${closed.map((c) => `${c.edge} (${c.cause})`).join(', ')}`]);
    }
    const key = JSON.stringify(list);
    if (key === this._bannerKey) return;
    this._bannerKey = key;
    this.banners.innerHTML = '';
    for (const [kind, text] of list) this.banners.append(h('div', { class: `banner ${kind}` }, text));
  }

  renderOverlay() {
    const o = this.overlay;
    const s = this.status;
    const show = (html, soft = false, actions = []) => {
      o.hidden = false;
      o.className = `vp-overlay${soft ? ' soft' : ''}`;
      o.innerHTML = '';
      o.append(...html);
      if (actions.length) {
        o.style.pointerEvents = 'auto';
        o.append(h('div', { style: { display: 'flex', gap: '8px' } }, ...actions));
      } else o.style.pointerEvents = soft ? 'none' : 'auto';
    };
    if (!this.booted) return; // the boot message from index.html stays
    if (this.connected === false) return show([h('div', { class: 'spinner' }), h('div', {}, 'Lost the connection to the twin server. Reconnecting…')], true);
    if (!s) return show([h('div', { class: 'spinner' }), h('div', {}, 'Connecting…')], true);
    const btn = (label, cls, fn) => h('button', { class: `btn ${cls}`, onclick: fn }, label);
    switch (s.state) {
      case 'idle':
        return show([h('div', {}, 'No simulation running yet.')], true, [btn('Start', 'primary', () => this.ctx.topbar.start())]);
      case 'loading':
        return show([h('div', { class: 'spinner' }), h('div', {}, s.message || 'Starting SUMO…')], true);
      case 'error':
        return show([h('div', { style: { maxWidth: '560px', color: '#ffd0d0' } }, s.error || 'Something went wrong.')], false, [btn('Try again', 'primary', () => this.ctx.topbar.start())]);
      case 'finished': {
        const sum = s.summary || {};
        const items = [
          ['mean delay', sum.mean_delay_s != null ? `${fmtNum(sum.mean_delay_s, 1)} s/veh` : '–'],
          ['completed trips', fmtNum(sum.completed, 0)],
          ['unfinished', sum.unfinished_pct != null ? `${fmtNum(sum.unfinished_pct, 1)}%` : '–'],
          ['p95 travel time', sum.p95_travel_time_s != null ? `${fmtNum(sum.p95_travel_time_s, 0)} s` : '–'],
          ['EV travel time', sum.ev_mean_travel_time_s != null ? `${fmtNum(sum.ev_mean_travel_time_s, 0)} s` : '–'],
        ];
        return show(
          [
            h('div', { style: { fontWeight: 700, fontSize: '16px' } }, 'Run finished'),
            h('div', { style: { color: '#8b9ab3' } }, this.ctx.static ? 'End of the recording. Replay it, or pick another run above.' : `Outputs saved to ${s.output_dir || 'results/twin/'}`),
            h('div', { class: 'chips', style: { justifyContent: 'center', maxWidth: '520px' } }, ...items.map(([k, v]) => h('span', { class: 'chip' }, `${k}: ${v}`))),
          ],
          false,
          [btn('Run again', 'primary', () => this.ctx.socket.control('reset')), btn('Close', '', () => (o.hidden = true))],
        );
      }
      default:
        o.hidden = true;
    }
  }

  buildLegend() {
    const root = $('#legend');
    const item = (sw, label) => h('div', { class: 'legend-item' }, sw, label);
    const sw = (bg, cls = '') => h('span', { class: `sw ${cls}`, style: { background: bg } });
    const body = h('div', { class: 'legend-body' },
      item(sw('#c9ccd1'), 'Car'),
      item(sw('#2f9bff', 'round'), 'Shares nav-app data'),
      item(sw('#d9dcdf'), 'Truck'),
      item(sw('#eef2f4'), 'Bus'),
      item(sw('linear-gradient(90deg,#ff2020 50%,#2a6bff 50%)'), 'Ambulance'),
      item(sw('#c42019'), 'Fire truck'),
      item(sw('#ff2a1f', 'round'), 'Brake lights'),
      item(sw('linear-gradient(90deg,#22e07a,#ffc533,#ff3b3b)'), 'Stop bar = signal'),
      item(sw('linear-gradient(90deg,#22c55e,#fbbf24,#ef4444)'), 'Queue length'),
      item(sw('#3a7cc0'), 'Flooded / closed'),
      item(sw('#b070ff'), 'Fake phone reports'),
      item(h('span', { class: 'sw round', style: { background: 'transparent', boxShadow: 'inset 0 0 0 2px #ff3030' } }), 'EV priority'),
    );
    const head = h('h3', {}, 'Legend', h('span', {}, '▾'));
    head.addEventListener('click', () => root.classList.toggle('collapsed'));
    root.append(head, body);
    if (window.matchMedia('(max-width: 640px)').matches) root.classList.add('collapsed'); // phones: keep the road visible
  }
}
