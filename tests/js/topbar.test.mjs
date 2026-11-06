// TopBar session form under a fake DOM: what POST /api/session receives for URL deep links and
// sandbox launches (frontend-3 coverage default, frontend-2 start time, frontend-13 contract,
// ext-207 restart hint), and Play / Space after an error (frontend-5).
import test from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

import { installDom } from './support/fake_dom.mjs';

register('./support/three_loader.mjs', import.meta.url);
installDom();
const { TopBar } = await import('../../teamb/twin/static/js/ui/topbar.js');
const { Bus } = await import('../../teamb/twin/static/js/ui/dom.js');
const { urlConfig } = await import('../../teamb/twin/static/js/launch.js');

const META = {
  scenarios: [
    { name: 'rush_hour', warmup: 900, events: [], defaults: {} },
    { name: 'fake_data_attack', warmup: 900, events: [{ time: 1500, kind: 'start_attack', params: {} }], defaults: { coverage: 0.25 } },
    { name: 'emergency', warmup: 900, events: [] },
  ],
  controllers: [{ name: 'fixed_time' }, { name: 'max_pressure' }, { name: 'max_pressure_probe' }],
  speeds: [1, 2, 5, 'max'],
};

function makeTopBar() {
  installDom(); // fresh elements for every top bar
  const posted = [];
  const ctx = {
    meta: META,
    static: null,
    bus: new Bus(),
    api: { post: async (path, body) => { posted.push({ path, body }); return { ok: true }; } },
    socket: { control: async () => ({ ok: true }), command: async () => ({ ok: true }) },
  };
  const bar = new TopBar(ctx);
  return { bar, posted, ctx };
}

/** A running session as /api/state reports it. */
const running = (config, extra = {}) => ({
  state: 'running', sid: extra.sid ?? 1, speed: 2, end_time: 3600, warmup: 900,
  config: { scenario: 'rush_hour', controller: 'max_pressure', seed: 1, coverage: null, ev_preemption: true, end_time: null, scenario_params: {}, start_at: 240, ...config },
  ...extra,
});

test('a deep link to fake_data_attack starts at its 25 % design coverage', async () => {
  const { bar, posted } = makeTopBar();
  bar.setForm({ scenario: 'fake_data_attack' });
  await bar.start();
  assert.equal(posted.at(-1).body.coverage, 0.25);
});

test("a link naming a scenario does not inherit the previous session's coverage or demand", async () => {
  const { bar, posted, ctx } = makeTopBar();
  ctx.bus.emit('status', running({ coverage: 0.5, scenario_params: { demand_scale: 1.25 }, end_time: 1800 }));
  assert.equal(bar.el.coverage.value, '50');
  const want = { scenario: 'fake_data_attack', controller: 'max_pressure_probe' };
  bar.setForm(want);
  await bar.start(want);
  const body = posted.at(-1).body;
  assert.equal(body.coverage, 0.25);
  assert.equal(body.scenario_params, undefined);
  assert.equal(body.end_time, undefined);
});

test('a session that ran with coverage None shows the scenario default', () => {
  const { bar, ctx } = makeTopBar();
  bar.setCoverageSlider(0.6);
  ctx.bus.emit('status', running({ scenario: 'fake_data_attack', coverage: null }));
  assert.equal(bar.el.coverage.value, '25');
});

test('a sandbox launch URL posts exactly the exported run, from t = 0', async () => {
  const { bar, posted, ctx } = makeTopBar();
  ctx.bus.emit('status', running({ coverage: 0.5 })); // whatever the shared instance ran before
  const want = urlConfig(new URLSearchParams('scenario=fake_data_attack&controller=max_pressure&seed=7&demand=1.25&end=1200&ev=0&start=0&speed=2'));
  bar.setForm(want);
  await bar.start(want);
  const body = posted.at(-1).body;
  assert.equal(posted.at(-1).path, '/api/session');
  assert.deepEqual(
    { scenario: body.scenario, controller: body.controller, seed: body.seed, start_at: body.start_at, end_time: body.end_time, ev_preemption: body.ev_preemption, scenario_params: body.scenario_params, coverage: body.coverage, speed: body.speed },
    { scenario: 'fake_data_attack', controller: 'max_pressure', seed: 7, start_at: 0, end_time: 1200, ev_preemption: false, scenario_params: { demand_scale: 1.25 }, coverage: 0.25, speed: 2 },
  );
});

test('an end time before the start time starts from 0 instead of finishing at once', async () => {
  const { bar, posted } = makeTopBar();
  bar.setForm({ scenario: 'rush_hour' });
  assert.equal(bar.el.start.value, '240'); // the "4:00 · traffic built up" default
  const want = { scenario: 'rush_hour', end_time: 120 };
  bar.setForm(want);
  await bar.start(want);
  assert.equal(posted.at(-1).body.start_at, 0);
  bar.setForm({ scenario: 'rush_hour', end_time: 1800 });
  await bar.start();
  assert.equal(posted.at(-1).body.start_at, 240);
});

test('changing only the start time asks for a restart', () => {
  const { bar, ctx } = makeTopBar();
  ctx.bus.emit('status', running({ start_at: 240 }));
  assert.equal(bar.el.apply.textContent, 'Restart');
  bar.el.start.value = 900;
  bar.el.start.dispatch('change');
  assert.equal(bar.el.apply.textContent, 'Restart with changes');
  assert.ok(bar.el.apply.classList.contains('pulse'));
  bar.el.start.value = 240;
  bar.el.start.dispatch('change');
  assert.equal(bar.el.apply.textContent, 'Restart');
});

test('the step key does nothing once the run has finished', async () => {
  const { bar, ctx } = makeTopBar();
  let calls = 0;
  ctx.socket.control = async () => { calls += 1; return { ok: true }; };
  ctx.bus.emit('status', running({}, { state: 'finished' }));
  await bar.step();
  assert.equal(calls, 0);
  ctx.bus.emit('status', running({}, { state: 'paused', sid: 2 }));
  await bar.step();
  assert.equal(calls, 1);
});

// --- Play / Space after an error ---------------------------------------------------------------
const { ReplaySocket, staticApi } = await import('../../teamb/twin/static/js/replay.js');

test('Play after an error resumes the recording in the online demo and restarts the live twin', async () => {
  const { bar, posted, ctx } = makeTopBar();
  const controls = [];
  ctx.socket.control = async (action) => { controls.push(action); return { ok: true }; };
  ctx.static = { data: 'data/' };
  ctx.bus.emit('status', running({}, { state: 'error', error: 'Could not load the next part of the recording' }));
  await bar.togglePlay();
  assert.deepEqual(controls, ['play']); // load the failed part again, where it stopped
  assert.equal(posted.length, 0);
  ctx.bus.emit('status', { state: 'error', sid: 2, config: null, error: 'Could not load the recording' });
  await bar.togglePlay();
  assert.equal(posted.length, 1); // nothing loaded yet: start the run
  ctx.static = null; // the live twin: SUMO failed, so start it again
  ctx.bus.emit('status', running({}, { state: 'error', sid: 3 }));
  await bar.togglePlay();
  assert.deepEqual(controls, ['play']);
  assert.equal(posted.length, 2);
});

test('Space after a failed chunk download carries on at the failed moment, not the start time', async () => {
  installDom();
  const files = {
    'data/runs/r/run.json': {
      id: 'r', end_t: 10, chunk_s: 5, chunks: [{ t0: 0, t1: 4, file: '000.json' }, { t0: 5, t1: 10, file: '001.json' }],
      ids: [], kinds: [], events: [], kpi_history: [],
      status: { config: { scenario: 'emergency', controller: 'max_pressure', seed: 1 }, step_length: 1, end_time: 10, warmup: 0 },
    },
    'data/runs/r/000.json': { t0: 0, frames: [0, 1, 2, 3, 4].map((t) => ({ t, v: [] })) },
    'data/runs/r/001.json': 503,
  };
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const body = files[url];
    if (body === undefined || typeof body === 'number') return { ok: false, status: body ?? 404, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => structuredClone(body) };
  };
  const meta = {
    ...META,
    scenarios: [{ name: 'emergency', warmup: 0, events: [] }],
    controllers: [{ name: 'max_pressure' }],
    demo: { runs: [{ id: 'r', scenario: 'emergency', controller: 'max_pressure' }], default: { scenario: 'emergency', controller: 'max_pressure' } },
  };
  const socket = new ReplaySocket(meta, 'data/');
  const clock = { ms: 0 };
  socket.now = () => clock.ms;
  const api = staticApi('data/');
  api.player = socket;
  const sessions = [];
  const post = api.post.bind(api);
  api.post = (path, body) => { sessions.push(body); return post(path, body); };
  const bus = new Bus();
  socket.on('status', (s) => bus.emit('status', s));
  socket.on('hello', (m) => bus.emit('status', m.status));
  const bar = new TopBar({ meta, static: { data: 'data/' }, bus, api, socket });
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  try {
    bar.setForm({ scenario: 'emergency', controller: 'max_pressure', start_at: 2 });
    await bar.start();
    assert.equal(socket.t, 2);
    for (let k = 0; k < 10 && socket.state === 'running'; k++) {
      clock.ms += 1000; // needs chunk 1 (t >= 5), which fails
      socket.tick();
      await settle();
    }
    assert.equal(socket.state, 'error');
    const at = socket.t;
    assert.ok(at > 2, `playback got past the start time before failing (t = ${at})`);
    files['data/runs/r/001.json'] = { t0: 5, frames: [5, 6, 7, 8, 9, 10].map((t) => ({ t, v: [] })) };
    await bar.togglePlay(); // the Space key
    assert.equal(socket.state, 'running');
    assert.equal(socket.t, at);
    assert.equal(sessions.length, 1); // no new POST /api/session
  } finally {
    socket.stopClock();
    globalThis.fetch = realFetch;
  }
});
