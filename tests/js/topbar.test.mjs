// TopBar session form under a fake DOM: what POST /api/session receives for URL deep links and
// sandbox launches (frontend-3 coverage default, frontend-2 start time, frontend-13 contract,
// ext-207 restart hint).
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
