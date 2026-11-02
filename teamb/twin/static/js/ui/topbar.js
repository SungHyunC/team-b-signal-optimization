// Top bar: session setup (scenario, controller, seed, start time), live settings (navigation-app
// coverage, EV priority), playback (play/pause/step/reset, speed), the sim clock and the timeline.
import { addKo, controllerDescription, controllerLabel, lang, scenarioDescription, scenarioTitle, t } from '../i18n.js';
import { fmtClock } from '../util.js';
import { $, $$, fillSelect, h, toast } from './dom.js';

addKo({
  '{vehicle} {origin}→{destination}': '{vehicle} {origin}→{destination}',
  'Close {edge} ({cause})': '{edge} 폐쇄 ({cause})',
  'Reopen {edge}': '{edge} 재개통',
  'Fake data at {junction} {approach}': '{junction} {approach} 가짜 데이터',
  'Attack stops': '공격 종료',
  'As fast as SUMO can go': 'SUMO가 낼 수 있는 최고 속도',
  '{s} simulated seconds per second': '1초에 시뮬레이션 {s}초',
  Max: '최대',
  'The recordings use seed 1': '녹화는 시드 1로 만들었어요',
  'Fixed in the recording. Change it in the live twin (python -m teamb twin).': '녹화에 고정된 값이에요. 실시간 트윈(python -m teamb twin)에서 바꿀 수 있어요.',
  'This page replays runs recorded with SUMO': 'SUMO로 녹화한 실행을 재생하는 페이지예요',
  'recorded demo': '녹화 데모',
  live: '실시간 연결',
  'reconnecting…': '다시 연결 중…',
  '0:00 · empty roads': '0:00 · 빈 도로',
  '4:00 · traffic built up': '4:00 · 차량이 찬 상태',
  '{time} · measurement starts': '{time} · 측정 시작',
  '{time} · before: {event}': '{time} · 직전: {event}',
  '{time} · custom': '{time} · 직접 지정',
  Start: '시작',
  Restart: '다시 시작',
  'Restart with changes': '바꾼 설정으로 다시 시작',
  'Starting {scenario} with {controller}…': '{scenario} · {controller} 시작 중…',
  'Could not start: {error}': '시작하지 못했어요: {error}',
  'Navigation-app coverage {pct}% (for vehicles departing from now on)': '내비 데이터 비율 {pct}% (지금부터 출발하는 차량에 적용)',
  'could not set coverage': '내비 데이터 비율을 바꾸지 못했어요',
  'Emergency-vehicle priority on': '긴급차량 우선 신호 켬',
  'Emergency-vehicle priority off': '긴급차량 우선 신호 끔',
  'could not change EV priority': '긴급차량 우선 신호를 바꾸지 못했어요',
  'could not change speed': '속도를 바꾸지 못했어요',
  'Fast-forwarding to {time}…': '{time}까지 빨리 감는 중…',
  'not running': '실행 전',
  'starting SUMO…': 'SUMO 시작 중…',
  error: '오류',
  'run finished': '실행 종료',
  'fast-forward → {time}': '빨리 감기 → {time}',
  'warm-up': '워밍업',
  measuring: '측정 중',
  'paused · {phase}': '일시정지 · {phase}',
  '{time} · {event} (click to jump just before it)': '{time} · {event} (클릭하면 직전으로 이동)',
  'measurement {from}–{to}': '측정 {from}–{to}',
  'SUMO cannot rewind. Restart this run and fast-forward to {time}?': 'SUMO는 되감을 수 없어요. 이 실행을 다시 시작해서 {time}까지 빨리 감을까요?',
});

const EVENT_COLORS = { dispatch_ev: '#ff4d4d', close_road: '#fb923c', reopen_road: '#22c55e', start_attack: '#a855f7', stop_attack: '#c4a5ff' };
const APPROACH_WORDS = { N: 'north', S: 'south', E: 'east', W: 'west' };

function eventLabel(e) {
  const p = e.params || {};
  switch (e.kind) {
    case 'dispatch_ev':
      return t('{vehicle} {origin}→{destination}', { vehicle: t(p.kind === 'firetruck' ? 'Fire truck' : 'Ambulance'), origin: p.origin || '', destination: p.destination || '' });
    case 'close_road':
      return t('Close {edge} ({cause})', { edge: p.edge, cause: t(p.cause || 'flood') });
    case 'reopen_road':
      return t('Reopen {edge}', { edge: p.edge });
    case 'start_attack': {
      const approach = p.approach || 'N'; // English keeps the letter (N), Korean says 북쪽
      return t('Fake data at {junction} {approach}', { junction: p.junction || 'J2', approach: lang === 'ko' ? t(APPROACH_WORDS[approach] || approach) : approach });
    }
    case 'stop_attack':
      return t('Attack stops');
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

    fillSelect(el.scenario, scenarios.map((s) => ({ value: s.name, label: scenarioTitle(s), title: scenarioDescription(s) })));
    this.fillControllerOptions();
    this.fillStartOptions();
    if (this.demo) {
      for (const x of [el.seed, el.coverage, el.ev]) x.disabled = true;
      el.seed.title = t('The recordings use seed 1');
      el.coverage.closest('label').title = el.ev.closest('label').title = t('Fixed in the recording. Change it in the live twin (python -m teamb twin).');
      el.conn.title = t('This page replays runs recorded with SUMO');
    }

    for (const s of meta.speeds) {
      const b = h('button', { 'data-speed': s, title: s === 'max' ? t('As fast as SUMO can go') : t('{s} simulated seconds per second', { s }) }, s === 'max' ? t('Max') : `${s}×`);
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
    ctx.bus.on('view', (name) => $$('.tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.view === name)));
    ctx.bus.on('status', (s) => this.onStatus(s));
    ctx.bus.on('frame', (f) => this.onFrame(f));
    ctx.bus.on('connection', (ok) => {
      el.conn.classList.toggle('ok', ok);
      el.conn.classList.toggle('bad', !ok);
      el.conn.querySelector('.conn-label').textContent = ok ? t(this.demo ? 'recorded demo' : 'live') : t('reconnecting…');
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
      list.map((c) => ({ value: c.name, label: controllerLabel(c), title: `${controllerDescription(c)}${c.owner ? ` — ${c.owner}` : ''}` })),
    );
  }

  fillStartOptions() {
    const sc = this.ctx.meta.scenarios.find((s) => s.name === this.el.scenario.value) || {};
    const warm = sc.warmup ?? 900;
    const opts = [
      { value: 0, label: t('0:00 · empty roads') },
      { value: 240, label: t('4:00 · traffic built up') },
      { value: warm, label: t('{time} · measurement starts', { time: fmtClock(warm) }) },
    ];
    for (const e of sc.events || []) {
      const at = Math.max(0, e.time - 30);
      opts.push({ value: at, label: t('{time} · before: {event}', { time: fmtClock(at), event: eventLabel(e) }) });
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
        el.start.append(h('option', { value: cfg.start_at }, t('{time} · custom', { time: fmtClock(cfg.start_at) })));
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
    this.el.apply.textContent = t(!running ? 'Start' : dirty ? 'Restart with changes' : 'Restart');
    this.el.apply.classList.toggle('pulse', !!dirty);
  }

  async start(extra = {}) {
    const cfg = { ...this.formConfig(), ...extra };
    try {
      await this.ctx.api.post('/api/session', cfg);
      const sc = this.ctx.meta.scenarios.find((s) => s.name === cfg.scenario);
      const ct = this.ctx.meta.controllers.find((c) => c.name === cfg.controller);
      toast(t('Starting {scenario} with {controller}…', { scenario: sc ? scenarioTitle(sc) : cfg.scenario, controller: ct ? controllerLabel(ct) : cfg.controller }));
    } catch (err) {
      toast(t('Could not start: {error}', { error: err.message }), 'error', 6000);
    }
  }

  // --- live settings -------------------------------------------------------------------
  async applyCoverage() {
    const share = Number(this.el.coverage.value) / 100;
    if (!this.isLive()) return; // used by the next start
    const r = await this.ctx.socket.command({ type: 'set_coverage', value: share });
    if (r.ok) toast(t('Navigation-app coverage {pct}% (for vehicles departing from now on)', { pct: Math.round(share * 100) }), 'ok');
    else toast(r.error || t('could not set coverage'), 'error');
  }

  async applyPreemption() {
    if (!this.isLive()) return;
    const enabled = this.el.ev.checked;
    const r = await this.ctx.socket.command({ type: 'set_preemption', enabled });
    if (r.ok) toast(t(enabled ? 'Emergency-vehicle priority on' : 'Emergency-vehicle priority off'), 'ok');
    else toast(r.error || t('could not change EV priority'), 'error');
  }

  isLive() {
    return this.status && ['running', 'paused'].includes(this.status.state);
  }

  // --- playback ---------------------------------------------------------------------------
  async setSpeed(speed) {
    const r = await this.ctx.socket.control('speed', { speed });
    if (!r.ok) toast(r.error || t('could not change speed'), 'error');
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

  async jump(at) {
    const r = await this.ctx.socket.control('jump', { t: at });
    if (!r.ok) toast(r.error, 'error');
    else if (!this.demo) toast(t('Fast-forwarding to {time}…', { time: fmtClock(at) }));
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
    let text = t('not running');
    let cls = '';
    if (s) {
      if (s.state === 'loading') text = t('starting SUMO…');
      else if (s.state === 'error') text = t('error');
      else if (s.state === 'finished') text = t('run finished');
      else if (s.fast_forward_to != null) {
        text = t('fast-forward → {time}', { time: fmtClock(s.fast_forward_to) });
        cls = 'ff';
      } else if (s.warmup != null) {
        const measuring = this.t >= s.warmup;
        const phase = t(measuring ? 'measuring' : 'warm-up');
        text = s.state === 'paused' ? t('paused · {phase}', { phase }) : phase;
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
        { class: 'tl-mark', style: { left: `${(100 * e.time) / end}%` }, title: t('{time} · {event} (click to jump just before it)', { time: fmtClock(e.time), event: eventLabel(e) }) },
        h('i', { style: { background: EVENT_COLORS[e.kind] || '#8b9ab3' } }),
      );
      m.addEventListener('click', (ev) => {
        ev.stopPropagation();
        this.jumpWithConfirm(Math.max(0, e.time - 20));
      });
      marks.append(m);
    }
    const lbl = (at, text) => marks.append(h('div', { class: 'tl-label', style: { left: `calc(${(100 * at) / end}% + 4px)` } }, text));
    if (s.warmup) lbl(0, t('warm-up'));
    if (s.warmup) lbl(s.warmup, t('measurement {from}–{to}', { from: fmtClock(s.warmup), to: fmtClock(end) }));
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

  jumpWithConfirm(at) {
    const s = this.status;
    if (!s || !['running', 'paused', 'finished'].includes(s.state)) return;
    if (!this.demo && (at < this.t || s.state === 'finished')) { // a recording can rewind, SUMO cannot
      const ok = confirm(t('SUMO cannot rewind. Restart this run and fast-forward to {time}?', { time: fmtClock(at) }));
      if (!ok) return;
    }
    this.jump(at);
  }
}
