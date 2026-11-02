// Top bar: session setup (scenario, controller, seed, start time), live settings (navigation-app
// coverage, EV priority), playback (play/pause/step/reset, speed), the sim clock and the timeline.
import { fmtClock } from '../util.js';
import { $, $$, fillSelect, h, toast } from './dom.js';

const EVENT_COLORS = { dispatch_ev: '#ff4d4d', close_road: '#fb923c', reopen_road: '#22c55e', start_attack: '#a855f7', stop_attack: '#c4a5ff' };

function eventLabel(e) {
  const p = e.params || {};
  switch (e.kind) {
    case 'dispatch_ev':
      return `${p.kind === 'firetruck' ? 'Fire truck' : 'Ambulance'} ${p.origin || ''}→${p.destination || ''}`;
    case 'close_road':
      return `Close ${p.edge} (${p.cause || 'flood'})`;
    case 'reopen_road':
      return `Reopen ${p.edge}`;
    case 'start_attack':
      return `Fake data at ${p.junction || 'J2'} ${p.approach || 'N'}`;
    case 'stop_attack':
      return 'Attack stops';
    default:
      return e.kind;
  }
}

export class TopBar {
  constructor(ctx) {
    this.ctx = ctx;
    this.status = null;
    this.t = 0;
    const { meta } = ctx;
    this.el = {
      scenario: $('#f-scenario'),
      controller: $('#f-controller'),
      seed: $('#f-seed'),
      start: $('#f-start'),
      apply: $('#btn-apply'),
      coverage: $('#f-coverage'),
      coverageVal: $('#f-coverage-val'),
      ev: $('#f-ev'),
      play: $('#btn-play'),
      step: $('#btn-step'),
      reset: $('#btn-reset'),
      speeds: $('#speed-buttons'),
      clockTime: $('#clock-time'),
      clockSub: $('#clock-sub'),
      conn: $('#conn'),
      timeline: $('#timeline'),
    };
    const el = this.el;
    // Online demo: only the recorded runs can be picked, and their settings are fixed.
    this.demo = ctx.static ? meta.demo : null;
    const scenarios = this.demo ? meta.scenarios.filter((s) => this.demo.runs.some((r) => r.scenario === s.name)) : meta.scenarios;

    fillSelect(el.scenario, scenarios.map((s) => ({ value: s.name, label: s.title || s.name, title: s.description })));
    this.fillControllerOptions();
    this.fillStartOptions();
    if (this.demo) {
      for (const x of [el.seed, el.coverage, el.ev]) x.disabled = true;
      el.seed.title = 'The recordings use seed 1';
      el.coverage.closest('label').title = el.ev.closest('label').title = 'Fixed in the recording. Change it in the live twin (python -m teamb twin).';
      el.conn.title = 'This page replays runs recorded with SUMO';
    }

    for (const s of meta.speeds) {
      const b = h('button', { 'data-speed': s, title: s === 'max' ? 'As fast as SUMO can go' : `${s} simulated seconds per second` }, s === 'max' ? 'Max' : `${s}×`);
      b.addEventListener('click', () => this.setSpeed(s));
      el.speeds.append(b);
    }

    el.scenario.addEventListener('change', () => {
      this.fillControllerOptions();
      this.fillStartOptions();
      // Each scenario has a design coverage (e.g. 25 % for the fake-data test): start from it.
      const sc = meta.scenarios.find((s) => s.name === el.scenario.value);
      const cov = sc && sc.defaults && sc.defaults.coverage != null ? sc.defaults.coverage : 1;
      this.setCoverageSlider(cov);
      this.markDirty();
    });
    for (const x of [el.controller, el.seed, el.start]) x.addEventListener('change', () => this.markDirty());
    el.apply.addEventListener('click', () => this.start());
    el.coverage.addEventListener('input', () => (el.coverageVal.textContent = `${el.coverage.value}%`));
    el.coverage.addEventListener('change', () => this.applyCoverage());
    el.ev.addEventListener('change', () => this.applyPreemption());
    el.play.addEventListener('click', () => this.togglePlay());
    el.step.addEventListener('click', () => this.step());
    el.reset.addEventListener('click', () => this.reset());
    el.timeline.addEventListener('click', (e) => this.onTimelineClick(e));

    for (const tab of $$('.tab')) tab.addEventListener('click', () => ctx.bus.emit('view', tab.dataset.view));
    ctx.bus.on('view', (name) => $$('.tab').forEach((t) => t.classList.toggle('active', t.dataset.view === name)));
    ctx.bus.on('status', (s) => this.onStatus(s));
    ctx.bus.on('frame', (f) => this.onFrame(f));
    ctx.bus.on('connection', (ok) => {
      el.conn.classList.toggle('ok', ok);
      el.conn.classList.toggle('bad', !ok);
      el.conn.querySelector('.conn-label').textContent = ok ? (this.demo ? 'recorded demo' : 'live') : 'reconnecting…';
    });
  }

  // --- the session form ---------------------------------------------------------------
  fillControllerOptions() {
    const { meta } = this.ctx;
    let list = meta.controllers;
    if (this.demo) {
      const names = this.demo.runs.filter((r) => r.scenario === this.el.scenario.value).map((r) => r.controller);
      list = names.map((name) => meta.controllers.find((c) => c.name === name) || { name });
    }
    fillSelect(
      this.el.controller,
      list.map((c) => ({ value: c.name, label: c.label || c.name, title: `${c.description || ''}${c.owner ? ` — ${c.owner}` : ''}` })),
    );
  }

  fillStartOptions() {
    const sc = this.ctx.meta.scenarios.find((s) => s.name === this.el.scenario.value) || {};
    const warm = sc.warmup ?? 900;
    const opts = [
      { value: 0, label: '0:00 · empty roads' },
      { value: 240, label: '4:00 · traffic built up' },
      { value: warm, label: `${fmtClock(warm)} · measurement starts` },
    ];
    for (const e of sc.events || []) {
      const t = Math.max(0, e.time - 30);
      opts.push({ value: t, label: `${fmtClock(t)} · before: ${eventLabel(e)}` });
    }
    const seen = new Set();
    fillSelect(
      this.el.start,
      opts.filter((o) => !seen.has(o.value) && seen.add(o.value)),
      this.el.start.value || 240,
    );
  }

  formConfig() {
    const el = this.el;
    return {
      scenario: el.scenario.value,
      controller: el.controller.value,
      seed: Number(el.seed.value) || 0,
      coverage: Number(el.coverage.value) / 100,
      ev_preemption: el.ev.checked,
      start_at: Number(el.start.value) || 0,
      speed: this.status ? this.status.speed : 2,
      autoplay: true,
    };
  }

  /** Apply values (e.g. from URL parameters) to the form. */
  setForm(cfg) {
    const el = this.el;
    if (cfg.scenario) {
      el.scenario.value = cfg.scenario;
      this.fillControllerOptions();
      this.fillStartOptions();
    }
    if (cfg.controller) el.controller.value = cfg.controller;
    if (cfg.seed != null) el.seed.value = cfg.seed;
    if (cfg.coverage != null) this.setCoverageSlider(cfg.coverage);
    if (cfg.ev_preemption != null) el.ev.checked = !!cfg.ev_preemption;
    if (cfg.start_at != null) {
      if (![...el.start.options].some((o) => Number(o.value) === Number(cfg.start_at))) {
        el.start.append(h('option', { value: cfg.start_at }, `${fmtClock(cfg.start_at)} · custom`));
      }
      el.start.value = cfg.start_at;
    }
  }

  setCoverageSlider(share) {
    const v = Math.round(Math.max(0.1, Math.min(1, share)) * 100);
    this.el.coverage.value = v;
    this.el.coverageVal.textContent = `${v}%`;
  }

  markDirty() {
    const s = this.status;
    const f = this.formConfig();
    const running = s && s.config && !['idle', 'error'].includes(s.state);
    const dirty = running && (f.scenario !== s.config.scenario || f.controller !== s.config.controller || f.seed !== s.config.seed);
    this.el.apply.textContent = !running ? 'Start' : dirty ? 'Restart with changes' : 'Restart';
    this.el.apply.classList.toggle('pulse', !!dirty);
  }

  async start(extra = {}) {
    const cfg = { ...this.formConfig(), ...extra };
    try {
      await this.ctx.api.post('/api/session', cfg);
      const sc = this.ctx.meta.scenarios.find((s) => s.name === cfg.scenario);
      toast(`Starting ${sc ? sc.title : cfg.scenario} with ${cfg.controller}…`);
    } catch (err) {
      toast(`Could not start: ${err.message}`, 'error', 6000);
    }
  }

  // --- live settings -------------------------------------------------------------------
  async applyCoverage() {
    const share = Number(this.el.coverage.value) / 100;
    if (!this.isLive()) return; // used by the next start
    const r = await this.ctx.socket.command({ type: 'set_coverage', value: share });
    if (r.ok) toast(`Navigation-app coverage ${Math.round(share * 100)}% (for vehicles departing from now on)`, 'ok');
    else toast(r.error || 'could not set coverage', 'error');
  }

  async applyPreemption() {
    if (!this.isLive()) return;
    const enabled = this.el.ev.checked;
    const r = await this.ctx.socket.command({ type: 'set_preemption', enabled });
    if (r.ok) toast(`Emergency-vehicle priority ${enabled ? 'on' : 'off'}`, 'ok');
    else toast(r.error || 'could not change EV priority', 'error');
  }

  isLive() {
    return this.status && ['running', 'paused'].includes(this.status.state);
  }

  // --- playback ---------------------------------------------------------------------------
  async setSpeed(speed) {
    const r = await this.ctx.socket.control('speed', { speed });
    if (!r.ok) toast(r.error || 'could not change speed', 'error');
  }

  async togglePlay() {
    const s = this.status;
    if (!s || ['idle', 'finished', 'error'].includes(s.state)) return this.start();
    const action = s.state === 'running' ? 'pause' : 'play';
    const r = await this.ctx.socket.control(action);
    if (!r.ok) toast(r.error, 'error');
  }

  async step() {
    const r = await this.ctx.socket.control('step');
    if (!r.ok) toast(r.error, 'error');
  }

  async reset() {
    if (!this.status || !this.status.config) return this.start();
    const r = await this.ctx.socket.control('reset');
    if (!r.ok) toast(r.error, 'error');
  }

  async jump(t) {
    const r = await this.ctx.socket.control('jump', { t });
    if (!r.ok) toast(r.error, 'error');
    else toast(`Fast-forwarding to ${fmtClock(t)}…`);
  }

  // --- status and frames ----------------------------------------------------------------
  onStatus(s) {
    this.status = s;
    const el = this.el;
    el.play.classList.toggle('playing', s.state === 'running');
    for (const b of el.speeds.children) b.classList.toggle('active', String(b.dataset.speed) === String(s.speed));
    // Show a new session's settings once; after that the form belongs to whoever edits it.
    if (s.config && ['loading', 'running', 'paused'].includes(s.state) && this.isNewSession(s.sid)) this.setForm(s.config);
    this.markDirty();
    this.renderTimeline();
    this.renderClock();
    const busy = s.state === 'loading';
    el.step.disabled = busy || !['running', 'paused'].includes(s.state);
    el.reset.disabled = busy || !s.config;
  }

  isNewSession(sid) {
    if (this._formSid === sid) return false;
    this._formSid = sid;
    return true;
  }

  onFrame(f) {
    this.t = f.t;
    if (document.activeElement !== this.el.coverage && f.coverage != null) this.setCoverageSlider(f.coverage);
    if (document.activeElement !== this.el.ev && f.ev_preemption != null) this.el.ev.checked = !!f.ev_preemption;
    this.renderClock();
    this.renderCursor();
  }

  renderClock() {
    const s = this.status;
    const el = this.el;
    el.clockTime.textContent = s && s.state !== 'idle' ? fmtClock(this.t) : '--:--';
    let text = 'not running';
    let cls = '';
    if (s) {
      if (s.state === 'loading') text = 'starting SUMO…';
      else if (s.state === 'error') text = 'error';
      else if (s.state === 'finished') text = 'run finished';
      else if (s.fast_forward_to != null) {
        text = `fast-forward → ${fmtClock(s.fast_forward_to)}`;
        cls = 'ff';
      } else if (s.warmup != null) {
        const measuring = this.t >= s.warmup;
        text = `${s.state === 'paused' ? 'paused · ' : ''}${measuring ? 'measuring' : 'warm-up'}`;
        cls = measuring ? 'measuring' : 'warmup';
      }
    }
    el.clockSub.textContent = text;
    el.clockSub.className = `clock-sub ${cls}`;
  }

  // --- timeline -------------------------------------------------------------------------
  renderTimeline() {
    const s = this.status;
    const tl = this.el.timeline;
    const marks = tl.querySelector('.tl-marks');
    marks.innerHTML = '';
    if (!s || !s.end_time) return;
    const end = s.end_time;
    tl.querySelector('.tl-warmup').style.width = `${(100 * Math.min(s.warmup || 0, end)) / end}%`;
    const events = (s.scenario && s.scenario.events) || [];
    for (const e of events) {
      if (e.time > end) continue;
      const m = h(
        'div',
        { class: 'tl-mark', style: { left: `${(100 * e.time) / end}%` }, title: `${fmtClock(e.time)} · ${eventLabel(e)} (click to jump just before it)` },
        h('i', { style: { background: EVENT_COLORS[e.kind] || '#8b9ab3' } }),
      );
      m.addEventListener('click', (ev) => {
        ev.stopPropagation();
        this.jumpWithConfirm(Math.max(0, e.time - 20));
      });
      marks.append(m);
    }
    const lbl = (t, text) => marks.append(h('div', { class: 'tl-label', style: { left: `calc(${(100 * t) / end}% + 4px)` } }, text));
    if (s.warmup) lbl(0, 'warm-up');
    if (s.warmup) lbl(s.warmup, `measurement ${fmtClock(s.warmup)}–${fmtClock(end)}`);
    this.renderCursor();
  }

  renderCursor() {
    const s = this.status;
    if (!s || !s.end_time) return;
    const tl = this.el.timeline;
    const k = Math.min(1, this.t / s.end_time);
    tl.querySelector('.tl-progress').style.width = `${100 * k}%`;
    tl.querySelector('.tl-cursor').style.left = `${100 * k}%`;
    const ff = tl.querySelector('.tl-ff');
    if (s.fast_forward_to != null && s.fast_forward_to > this.t) {
      ff.style.left = `${100 * k}%`;
      ff.style.width = `${(100 * (s.fast_forward_to - this.t)) / s.end_time}%`;
    } else ff.style.width = '0';
  }

  onTimelineClick(e) {
    const s = this.status;
    if (!s || !s.end_time) return;
    const track = this.el.timeline.querySelector('.tl-track').getBoundingClientRect();
    const k = Math.max(0, Math.min(1, (e.clientX - track.left) / track.width));
    this.jumpWithConfirm(Math.round(k * s.end_time));
  }

  jumpWithConfirm(t) {
    const s = this.status;
    if (!s || !['running', 'paused', 'finished'].includes(s.state)) return;
    if (!this.demo && (t < this.t || s.state === 'finished')) { // a recording can rewind, SUMO cannot
      const ok = confirm(`SUMO cannot rewind. Restart this run and fast-forward to ${fmtClock(t)}?`);
      if (!ok) return;
    }
    this.jump(t);
  }
}
