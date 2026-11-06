// launch.js: URL settings -> session config, and when opening a link restarts the shared run
// (frontend-1, twin-security-2, ext-178, frontend-2, frontend-3, and scenario defaults of a
// sandbox launch link).
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  configDiffers,
  sameValue,
  scenarioDefaultCoverage,
  stateParams,
  stripLaunchParams,
  urlConfig,
  withSafeStart,
} from '../../teamb/twin/static/js/launch.js';

const q = (s) => new URLSearchParams(s);
/** What /api/state sends: SessionConfig.to_dict() after a JSON round trip (floats like 300.0 -> 300). */
const serverConfig = (over = {}) =>
  JSON.parse(
    JSON.stringify({
      scenario: 'rush_hour', controller: 'max_pressure', seed: 1, coverage: null, ev_preemption: true,
      sampling: 'uniform', end_time: null, controller_params: {}, scenario_params: {}, speed: '2',
      autoplay: true, start_at: 0, ...over,
    }),
  );

test('urlConfig parses every run parameter', () => {
  assert.deepEqual(urlConfig(q('?scenario=emergency&controller=coordinated&seed=3&coverage=25&start=1170&speed=max&ev=0&demand=1.25&end=1200')), {
    scenario: 'emergency', controller: 'coordinated', seed: 3, coverage: 0.25, start_at: 1170, speed: 'max',
    ev_preemption: false, scenario_params: { demand_scale: 1.25 }, end_time: 1200,
  });
  assert.equal(urlConfig(q('?coverage=0.5')).coverage, 0.5);
  assert.deepEqual(urlConfig(q('?lang=ko&camera=J2')), {});
});

test('sameValue compares JSON values by content', () => {
  assert.ok(sameValue({ demand_scale: 1.2 }, { demand_scale: 1.2 }));
  assert.ok(sameValue({ a: 1, b: { c: [1, 2] } }, { b: { c: [1, 2] }, a: 1 }));
  assert.ok(!sameValue({ demand_scale: 1.5 }, { demand_scale: 1.2 }));
  assert.ok(!sameValue({ demand_scale: 1 }, {}));
  assert.ok(!sameValue({}, null));
  assert.ok(!sameValue([1], { 0: 1 }));
  assert.ok(sameValue(null, null));
  assert.ok(!sameValue(1, '1'));
});

test('reloading a sandbox launch link does not restart the identical run', () => {
  const want = urlConfig(q('?scenario=rush_hour&controller=max_pressure&seed=1&demand=1&end=1200&ev=1&start=0&speed=2'));
  const running = serverConfig({ scenario_params: { demand_scale: 1 }, end_time: 1200.0 });
  assert.equal(configDiffers(want, running), false);
});

test('a different demand, scenario or end time does restart', () => {
  const running = serverConfig({ scenario_params: { demand_scale: 1.25 }, end_time: 1200 });
  assert.equal(configDiffers(urlConfig(q('?scenario=rush_hour&demand=1.5&end=1200')), running), true);
  assert.equal(configDiffers(urlConfig(q('?scenario=off_peak&demand=1.25&end=1200')), running), true);
  assert.equal(configDiffers(urlConfig(q('?scenario=rush_hour&demand=1.25&end=1800')), running), true);
  assert.equal(configDiffers(urlConfig(q('?scenario=rush_hour&demand=1.25&end=1200')), running), false);
});

// A sandbox launch link (sandbox_schema.js launchParams) names the whole run: a blank duration
// means the scenario's own, it never names coverage, and it always sends demand.
const META = { scenarios: [{ name: 'rush_hour', defaults: {} }, { name: 'fake_data_attack', defaults: { coverage: 0.25 } }] };
const sandboxLink = (extra = '') => urlConfig(q(`?scenario=rush_hour&controller=max_pressure&seed=1&demand=1&ev=1&start=0&speed=2${extra}`));

test("a link naming a scenario does not attach to a run with another duration or coverage", () => {
  assert.equal(configDiffers(sandboxLink(), serverConfig({ end_time: 1200 }), META), true);
  assert.equal(configDiffers(sandboxLink(), serverConfig({ coverage: 0.5 }), META), true);
  assert.equal(configDiffers(sandboxLink('&end=1200'), serverConfig({ end_time: 1200, coverage: 0.5 }), META), true);
  assert.equal(configDiffers(urlConfig(q('?scenario=rush_hour&controller=max_pressure')), serverConfig({ end_time: 1200 }), META), true);
});

test('demand 1 and the scenario coverage are the same run as leaving them out', () => {
  assert.equal(configDiffers(sandboxLink(), serverConfig({ scenario_params: {} }), META), false);
  assert.equal(configDiffers(sandboxLink(), serverConfig({ coverage: 1 }), META), false); // a form-started run
  const attack = urlConfig(q('?scenario=fake_data_attack&controller=max_pressure&seed=1&demand=1'));
  const attackRun = (over) => serverConfig({ scenario: 'fake_data_attack', ...over });
  assert.equal(configDiffers(attack, attackRun({ coverage: 0.25 }), META), false);
  assert.equal(configDiffers(attack, attackRun({ coverage: null }), META), false);
  assert.equal(configDiffers(attack, attackRun({ coverage: 1 }), META), true);
  assert.equal(configDiffers(urlConfig(q('?scenario=fake_data_attack&coverage=25')), attackRun({ coverage: null }), META), false);
});

test('a link without a scenario still leaves coverage, duration and demand to the running run', () => {
  const running = serverConfig({ coverage: 0.5, end_time: 1200, scenario_params: { demand_scale: 1.25 } });
  assert.equal(configDiffers(urlConfig(q('?speed=max&camera=J2')), running, META), false);
  assert.equal(configDiffers(urlConfig(q('?controller=max_pressure&seed=1')), running, META), false);
  assert.equal(configDiffers(urlConfig(q('?controller=fixed_time')), running, META), true);
});

test('speed and start time alone never restart; no running config never "differs"', () => {
  const running = serverConfig({ start_at: 0 });
  assert.equal(configDiffers({ scenario: 'rush_hour', start_at: 900, speed: 'max' }, running), false);
  assert.equal(configDiffers({ scenario: 'rush_hour' }, null), false);
});

test('the language switch URL names the running run exactly, so the reload attaches', () => {
  const config = serverConfig({ scenario_params: { demand_scale: 1.25 }, end_time: 1500, coverage: 0.25, ev_preemption: false });
  const status = { state: 'running', speed: '5', config };
  const params = stateParams(status, { t: 1234.6 });
  assert.deepEqual(params, {
    scenario: 'rush_hour', controller: 'max_pressure', seed: 1, start: 1234, speed: '5', coverage: 0.25, ev: 0, demand: 1.25, end: 1500,
  });
  // Rebuild the URL the way switchLanguage does (null deletes) on top of a stale earlier link.
  const url = new URL('https://twin.example/?scenario=off_peak&demand=2&end=900&lang=en');
  for (const [k, v] of Object.entries(stateParams({ ...status, config: serverConfig() }, { t: 10 }))) {
    if (v == null || v === '') url.searchParams.delete(k);
    else url.searchParams.set(k, v);
  }
  assert.equal(url.searchParams.has('demand'), false);
  assert.equal(url.searchParams.has('end'), false);
  assert.equal(configDiffers(urlConfig(url.searchParams), serverConfig()), false);
  assert.equal(configDiffers(urlConfig(new URLSearchParams(new URLSearchParams(Object.entries(params)).toString())), config), false);
  assert.deepEqual(stateParams({ state: 'idle', config }, null), {});
  assert.equal(stateParams({ state: 'finished', speed: 2, config: { ...config, start_at: 240 } }, { t: 3000 }).start, 240);
});

test('stripLaunchParams keeps view parameters only', () => {
  assert.equal(stripLaunchParams('https://x.example/?scenario=a&controller=b&seed=1&demand=1&end=1200&ev=1&start=0&speed=2&coverage=1'), '/');
  assert.equal(stripLaunchParams('https://x.example/twin/?lang=ko&scenario=a&camera=J2&present=1#h'), '/twin/?lang=ko&camera=J2&present=1#h');
});

test('scenario design coverage, 1 when the scenario has none', () => {
  const meta = { scenarios: [{ name: 'fake_data_attack', defaults: { coverage: 0.25 } }, { name: 'rush_hour', defaults: {} }, { name: 'emergency' }] };
  assert.equal(scenarioDefaultCoverage(meta, 'fake_data_attack'), 0.25);
  assert.equal(scenarioDefaultCoverage(meta, 'rush_hour'), 1);
  assert.equal(scenarioDefaultCoverage(meta, 'emergency'), 1);
  assert.equal(scenarioDefaultCoverage(meta, 'unknown'), 1);
  assert.equal(scenarioDefaultCoverage(null, 'x'), 1);
});

test('a start time at or after the end time starts from 0 instead of finishing at once', () => {
  assert.equal(withSafeStart({ start_at: 240, end_time: 120 }).start_at, 0);
  assert.equal(withSafeStart({ start_at: 120, end_time: 120 }).start_at, 0);
  assert.equal(withSafeStart({ start_at: 240, end_time: 1200 }).start_at, 240);
  assert.equal(withSafeStart({ start_at: 240 }).start_at, 240);
  assert.equal(withSafeStart({ start_at: 240, end_time: null }).start_at, 240);
});
