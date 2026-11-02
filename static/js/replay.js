// Online demo (GitHub Pages): plays runs recorded by teamb/twin/site.py through the same
// interface as TwinSocket in net.js, so the rest of the app cannot tell a recording from the
// live server. Static hosting has no SUMO, so live commands (dispatch an ambulance, close a
// road, fake data, approve an AI plan) answer with a pointer to the local twin.
//
// A run is data/runs/<id>/run.json (status, vehicle ids, all events, KPI history, chunk list)
// plus one file per 5 simulated minutes, fetched when playback gets there. Inside a chunk the
// vehicles are delta-encoded (decodeVehicles undoes encode_vehicles in site.py) and fields that
// did not change since the previous frame are left out (carried over here).

import { addKo, t } from './i18n.js';

addKo({
  'This online demo replays recorded runs. To dispatch vehicles, close roads, fake data or approve AI plans yourself, run the live twin: python -m teamb twin (see the README).':
    '이 온라인 데모는 녹화된 실행을 재생해요. 긴급차량 출동, 도로 폐쇄, 가짜 데이터, AI 계획 승인을 직접 해 보려면 실시간 트윈을 실행하세요: python -m teamb twin (README 참고).',
  'Loading the recorded run…': '녹화된 실행을 불러오는 중…',
  'Could not load the recording ({error}). Reload the page to try again.': '녹화를 불러오지 못했어요 ({error}). 페이지를 새로고침해 주세요.',
  'Could not load the next part of the recording ({error}).': '녹화의 다음 부분을 불러오지 못했어요 ({error}).',
  'no recorded run is loaded yet': '아직 불러온 녹화가 없어요',
});

const FPS = 12; // frames per wall second at most, like the live server
const MAX_SPEED = 60; // "max" replays one simulated minute per second
const KEEP_CHUNKS = 4; // decoded chunks kept in memory
export const LIVE_ONLY = t(
  'This online demo replays recorded runs. To dispatch vehicles, close roads, fake data or approve AI plans yourself, run the live twin: python -m teamb twin (see the README).',
);

async function getJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

/** Same shape as `api` in net.js, answered from the files the build wrote. */
export function staticApi(base) {
  const files = { '/api/meta': 'meta.json', '/api/geometry': 'geometry.json', '/api/results': 'results.json' };
  const api = {
    player: null, // the ReplaySocket: POST /api/session starts a recorded run
    get(path) {
      return files[path] ? getJson(base + files[path]) : Promise.reject(new Error(`${path} is not part of the online demo`));
    },
    post(path, body) {
      if (path === '/api/session' && api.player) return api.player.start(body);
      return Promise.reject(new Error(LIVE_ONLY));
    },
  };
  return api;
}

/** Inverse of encode_vehicles in site.py: flat ints -> [[id, x, y, angle, speed, kind], ...]. */
export function decodeVehicles(flat, ids, kinds, prev) {
  const vehicles = [];
  const seen = new Map();
  for (let j = 0; j < flat.length; ) {
    let i = flat[j];
    let x, y, a, v, k;
    if (i < 0) {
      i = -i - 1;
      [x, y, a, v, k] = [flat[j + 1], flat[j + 2], flat[j + 3], flat[j + 4], flat[j + 5]];
      j += 6;
    } else {
      const p = prev.get(i);
      x = p[0] + flat[j + 1];
      y = p[1] + flat[j + 2];
      a = (p[2] + flat[j + 3] + 360) % 360;
      v = flat[j + 4];
      k = p[3];
      j += 5;
    }
    seen.set(i, [x, y, a, k]);
    vehicles.push([ids[i], x / 10, y / 10, a, v / 10, kinds[k]]);
  }
  return { vehicles, prev: seen };
}

export class ReplaySocket {
  constructor(meta, base) {
    this.meta = meta;
    this.base = base;
    this.runs = meta.demo.runs;
    this.handlers = new Map();
    this.connected = false;
    this.sid = 1;
    this.state = 'idle'; // idle | loading | running | paused | finished | error
    this.run = null; // run.json of the loaded run
    this.info = null; // its entry in meta.demo.runs
    this.config = null;
    this.message = null;
    this.error = null;
    this.speed = 2;
    this.playing = false;
    this.t = 0; // sim time of the frame on screen
    this.clock = null; // {wall, t}: sim time t was on screen at performance.now() = wall
    this.timer = null;
    this.waiting = false; // playback holds while a chunk downloads
    this.loads = new Map(); // chunk index -> Promise of decoded frames
    this.ready = new Map(); // chunk index -> decoded frames
  }

  // --- TwinSocket interface ---------------------------------------------------------
  on(type, fn) {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type).push(fn);
    return this;
  }

  emit(type, data) {
    for (const fn of this.handlers.get(type) || []) {
      try {
        fn(data);
      } catch (err) {
        console.error(`handler for '${type}' failed`, err);
      }
    }
  }

  connect() {
    this.connected = true;
    this.emit('open');
    this.emit('hello', { type: 'hello', status: this.status(), events: [], kpi_history: [] });
  }

  send(msg) {
    if (msg.type === 'control') return this.control(msg.action, msg);
    if (msg.type === 'command') return this.command(msg.command);
    return Promise.resolve({ ok: true });
  }

  async control(action, extra = {}) {
    if (extra.speed != null) this.setSpeed(extra.speed);
    if (!this.run) return { ok: false, error: t('no recorded run is loaded yet') };
    switch (action) {
      case 'speed':
        break;
      case 'play':
        if (this.state === 'finished') await this.seek(this.config.start_at, true);
        else this.resume();
        break;
      case 'pause':
        this.pause();
        break;
      case 'step':
        this.pause();
        await this.advanceTo(this.t + (this.run.status.step_length || 1));
        break;
      case 'reset':
        await this.seek(this.config.start_at, true);
        break;
      case 'jump':
        await this.seek(Number(extra.t) || 0, this.state === 'finished' || this.playing);
        break;
      default:
        return { ok: false, error: `unknown control action '${action}'` };
    }
    this.publishStatus();
    return { ok: true, state: this.state, speed: this.speed, t: this.t };
  }

  command() {
    return Promise.resolve({ ok: false, error: LIVE_ONLY, demo: true });
  }

  // --- runs -----------------------------------------------------------------------------
  /** POST /api/session: load the recorded run closest to cfg and show it from cfg.start_at. */
  async start(cfg = {}) {
    const info = this.pick(cfg.scenario, cfg.controller);
    if (!info) throw new Error('this build has no recorded runs');
    const sid = ++this.sid;
    this.stopClock();
    Object.assign(this, { state: 'loading', playing: false, run: null, info, config: null, error: null });
    this.message = t('Loading the recorded run…');
    this.publishStatus();
    let run;
    try {
      run = await getJson(`${this.base}runs/${info.id}/run.json`);
    } catch (err) {
      if (sid === this.sid) {
        Object.assign(this, { state: 'error', error: t('Could not load the recording ({error}). Reload the page to try again.', { error: err.message }) });
        this.publishStatus();
      }
      throw err;
    }
    if (sid !== this.sid) return { ok: false, error: 'a newer run was started' };
    this.run = run;
    this.loads.clear();
    this.ready.clear();
    if (cfg.speed != null) this.setSpeed(cfg.speed);
    const startAt = Math.max(0, Math.min(Number(cfg.start_at) || 0, run.end_t));
    this.config = { ...run.status.config, speed: this.speed, start_at: startAt };
    this.message = null;
    await this.seek(startAt, cfg.autoplay !== false);
    return { ok: true, sid: this.sid, run_id: run.status.run_id };
  }

  pick(scenario, controller) {
    const { runs } = this;
    const d = this.meta.demo.default;
    return (
      runs.find((r) => r.scenario === scenario && r.controller === controller) ||
      runs.find((r) => r.scenario === scenario) ||
      runs.find((r) => r.scenario === d.scenario && r.controller === d.controller) ||
      runs[0]
    );
  }

  status() {
    const base = this.run ? this.run.status : {};
    return {
      ...base,
      type: 'status',
      state: this.state,
      sid: this.sid,
      config: this.config,
      speed: this.speed,
      playing: this.playing,
      fast_forward_to: null,
      message: this.message,
      error: this.error,
      summary: this.state === 'finished' ? base.summary : null,
      fps: FPS,
      step_ms: null,
      output_dir: null,
      note: this.info ? this.info.note : null,
      note_ko: this.info ? this.info.note_ko : null,
      recorded: this.run ? this.run.recorded : null,
    };
  }

  publishStatus() {
    this.emit('status', this.status());
  }

  // --- playback -------------------------------------------------------------------------
  setSpeed(speed) {
    const value = speed === 'max' ? 'max' : Number(speed);
    if (value !== 'max' && !(value > 0)) return;
    this.speed = value;
    if (this.config) this.config.speed = value;
    if (this.clock) this.clock = { wall: performance.now(), t: this.t }; // keep the picture where it is
  }

  rate() {
    return this.speed === 'max' ? MAX_SPEED : this.speed;
  }

  resume() {
    this.playing = true;
    this.state = 'running';
    this.startClock();
  }

  pause() {
    this.stopClock();
    this.playing = false;
    this.state = 'paused';
  }

  startClock() {
    clearInterval(this.timer);
    this.clock = { wall: performance.now(), t: this.t };
    this.timer = setInterval(() => this.tick(), 1000 / FPS);
  }

  stopClock() {
    clearInterval(this.timer);
    this.timer = null;
    this.clock = null;
    this.waiting = false;
  }

  /** Show the run at sim time t: a new session for the panels (like the live "jump"), with the
   *  event log and KPI history up to t. Unlike SUMO, a recording can also go back in time. */
  async seek(t, play) {
    const run = this.run;
    t = Math.max(0, Math.min(Number(t) || 0, run.end_t));
    this.stopClock();
    const sid = ++this.sid;
    const i = this.chunkIndex(t);
    const frames = await this.loadChunk(i);
    if (sid !== this.sid) return;
    let frame = frames[0];
    for (const f of frames) if (f.t <= t) frame = f;
    this.t = frame.t;
    this.playing = play;
    this.state = play ? 'running' : 'paused';
    this.emit('hello', {
      type: 'hello',
      status: this.status(),
      events: run.events.filter((e) => e.t <= this.t),
      kpi_history: run.kpi_history.filter((k) => k.t <= this.t),
    });
    this.emitFrame(frame, []);
    if (play) this.startClock();
  }

  tick() {
    if (!this.playing || this.waiting || !this.clock) return;
    const run = this.run;
    const target = Math.min(run.end_t, this.clock.t + ((performance.now() - this.clock.wall) / 1000) * this.rate());
    const missing = [];
    for (let i = this.chunkIndex(this.t); i <= this.chunkIndex(target); i++) if (!this.ready.has(i)) missing.push(i);
    if (missing.length) {
      // Hold the picture until the data is here, then carry on from where it stopped.
      this.waiting = true;
      const sid = this.sid;
      Promise.all(missing.map((i) => this.loadChunk(i))).then(
        () => {
          if (sid !== this.sid || !this.playing) return;
          this.waiting = false;
          this.clock = { wall: performance.now(), t: this.t };
        },
        (err) => {
          if (sid !== this.sid) return;
          this.pause();
          this.error = t('Could not load the next part of the recording ({error}).', { error: err.message });
          this.publishStatus();
        },
      );
      return;
    }
    this.advance(target);
    const next = this.chunkIndex(this.t) + 1;
    if (next < run.chunks.length && this.t > run.chunks[next].t0 - run.chunk_s / 2) this.loadChunk(next).catch(() => {});
  }

  async advanceTo(target) {
    const sid = this.sid;
    const last = this.chunkIndex(Math.min(target, this.run.end_t));
    for (let i = this.chunkIndex(this.t); i <= last; i++) await this.loadChunk(i);
    if (sid === this.sid) this.advance(target);
  }

  /** Show the newest frame at or before target; events of the frames in between come along. */
  advance(target) {
    const run = this.run;
    target = Math.min(target, run.end_t);
    if (!(target > this.t)) return;
    const events = [];
    let shown = null;
    for (let i = this.chunkIndex(this.t); i < run.chunks.length && run.chunks[i].t0 <= target; i++) {
      for (const f of this.ready.get(i) || []) {
        if (f.t <= this.t || f.t > target) continue;
        events.push(...f.events);
        shown = f;
      }
    }
    if (!shown) return;
    this.t = shown.t;
    this.emitFrame(shown, events);
    if (this.t >= run.end_t) this.finish();
  }

  finish() {
    this.stopClock();
    this.playing = false;
    this.state = 'finished';
    this.publishStatus();
  }

  emitFrame(frame, events) {
    this.emit('frame', {
      ...frame,
      type: 'frame',
      sid: this.sid,
      scenario: this.run.scenario,
      controller: this.run.frame_controller,
      events,
    });
  }

  // --- data -------------------------------------------------------------------------------
  chunkIndex(t) {
    const { chunks } = this.run;
    let i = chunks.length - 1;
    while (i > 0 && chunks[i].t0 > t) i--;
    return i;
  }

  loadChunk(i) {
    if (!this.loads.has(i)) {
      const run = this.run;
      const p = getJson(`${this.base}runs/${run.id}/${run.chunks[i].file}`).then((chunk) => {
        const frames = this.decodeChunk(chunk, run);
        if (this.run === run) this.ready.set(i, frames);
        return frames;
      });
      p.catch(() => this.loads.delete(i)); // let a later tick try again
      this.loads.set(i, p);
      for (const k of [...this.loads.keys()]) {
        if (this.loads.size <= KEEP_CHUNKS) break;
        if (Math.abs(k - i) > 1) {
          this.loads.delete(k);
          this.ready.delete(k);
        }
      }
    }
    return this.loads.get(i);
  }

  decodeChunk(chunk, run) {
    let prev = new Map();
    let last = {};
    return chunk.frames.map(({ t, v, events, ...changed }) => {
      const decoded = decodeVehicles(v, run.ids, run.kinds, prev);
      prev = decoded.prev;
      last = { ...last, ...changed, t, vehicles: decoded.vehicles, events: events || [] };
      return last;
    });
  }
}
