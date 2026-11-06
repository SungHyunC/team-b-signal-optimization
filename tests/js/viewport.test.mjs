// viewport.js banners: the "FAKE DATA SUSPECTED" banner goes away 4 s after the last alert even
// when the run is paused and no frame or status arrives (ext-208), and the replay error overlay
// retries through TopBar.retry (frontend-5).
import test, { mock } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

import { installDom } from './support/fake_dom.mjs';

register('./support/three_loader.mjs', import.meta.url);
installDom();
const { ViewportChrome } = await import('../../teamb/twin/static/js/ui/viewport.js');
const { Bus } = await import('../../teamb/twin/static/js/ui/dom.js');

const META = { scenarios: [{ name: 'fake_data_attack', title: 'Fake data attack' }], controllers: [{ name: 'max_pressure_probe', label: 'Probe' }], junctions: ['J1', 'J2'] };
const ALERT = { type: 'probe_detector_mismatch', junction: 'J2', approach: 'N', probe_queue: 40, detector_queue: 2 };

function chrome(extra = {}) {
  const { get } = installDom();
  const bus = new Bus();
  const ctx = { meta: META, bus, static: null, socket: { control: async () => ({ ok: true }) }, topbar: { start: async () => {} }, ...extra };
  const view = new ViewportChrome(ctx);
  view.hideBootOverlay();
  return { view, bus, get, ctx };
}
const bannerText = (get) => get('banners').textContent;

test('the fake-data banner expires while paused', (t) => {
  mock.timers.enable({ apis: ['setTimeout'] });
  t.after(() => mock.timers.reset());
  let now = 1000;
  const realNow = performance.now;
  performance.now = () => now;
  t.after(() => (performance.now = realNow));

  const { bus, get } = chrome();
  bus.emit('status', { state: 'running', sid: 1, config: { scenario: 'fake_data_attack', controller: 'max_pressure_probe', seed: 1 } });
  bus.emit('frame', { t: 100, alerts: [ALERT] });
  assert.match(bannerText(get), /FAKE DATA SUSPECTED at J2/);
  bus.emit('status', { state: 'paused', sid: 1, config: { scenario: 'fake_data_attack', controller: 'max_pressure_probe', seed: 1 } });
  assert.match(bannerText(get), /FAKE DATA SUSPECTED/); // still within the 4 s hold
  now += 4100;
  mock.timers.tick(4100); // nothing else arrives while paused
  assert.equal(bannerText(get), '');
});

test("a new session drops the previous run's alert", (t) => {
  let now = 1000;
  const realNow = performance.now;
  performance.now = () => now;
  t.after(() => (performance.now = realNow));
  const { bus, get } = chrome();
  bus.emit('frame', { t: 100, alerts: [ALERT] });
  assert.match(bannerText(get), /FAKE DATA SUSPECTED/);
  bus.emit('session', {});
  bus.emit('frame', { t: 0 });
  assert.equal(bannerText(get), '');
});

test('the error overlay retries through TopBar.retry, the same path as Play / Space', async () => {
  // TopBar.retry resumes a recording where its download failed (tests/js/topbar.test.mjs).
  const calls = [];
  const topbar = { retry: async () => calls.push('retry'), start: async () => calls.push('start') };
  const { bus, get } = chrome({ static: { data: 'data/' }, socket: { control: async (a) => calls.push(a) }, topbar });
  bus.emit('connection', true);
  bus.emit('status', { state: 'error', sid: 3, error: 'Could not load the next part of the recording (data/runs/r/001.json: 503).', config: { scenario: 'fake_data_attack' } });
  const overlay = get('vp-overlay');
  assert.match(overlay.textContent, /001\.json: 503/);
  const buttons = overlay.children.at(-1).children;
  buttons[0].click();
  assert.deepEqual(calls, ['retry']);
  bus.emit('status', { state: 'error', sid: 4, error: 'Could not load the recording', config: null });
  get('vp-overlay').children.at(-1).children[0].click();
  assert.deepEqual(calls, ['retry', 'retry']);
});
