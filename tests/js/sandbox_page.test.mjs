// sandbox.js on a fake DOM, as on static GitHub Pages with storage blocked: the page builds,
// shows both commands, rejects an empty seed and short durations, and the live launch still
// works and starts at 0:00 (frontend-2, frontend-7, frontend-8, contract 5).
import test from 'node:test';
import assert from 'node:assert/strict';

import { installDom } from './support/fake_dom.mjs';

const IDS = [
  'lang-switch', 'scenario', 'controller', 'demand_scale', 'seed', 'duration_s', 'duration_hint', 'ev_preemption', 'reset', 'export',
  'import', 'schema_source', 'status', 'preview', 'copy', 'command_file', 'command', 'live_url', 'launch_live', 'launch_hint',
];
const { get } = installDom({ ids: IDS });
get('demand_scale').value = '1';
get('seed').value = '1';
get('ev_preemption').checked = true;

const assigned = [];
globalThis.location = { hostname: 'team-b.github.io', protocol: 'https:', origin: 'https://team-b.github.io', search: '' };
globalThis.window.location = { assign: (href) => assigned.push(href) };
// Chrome with all cookies blocked: any localStorage access throws.
Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('SecurityError: storage blocked'); } });
let fetched = 0;
globalThis.fetch = async () => { fetched += 1; return { ok: false, status: 404 }; };

await import('../../teamb/twin/static/js/sandbox.js');

const input = (id, value) => {
  get(id).value = value;
  get(id).dispatch('input');
};

test('the page builds from the built-in schema on GitHub Pages without asking a server', () => {
  assert.equal(get('scenario').options.length, 8);
  assert.equal(get('controller').value, 'max_pressure');
  assert.equal(get('duration_s').min, 1200);
  assert.equal(get('duration_s').max, 10800);
  assert.match(get('schema_source').textContent, /Built-in/);
  assert.equal(fetched, 0);
});

test('a valid form shows the JSON and both reproduction commands', () => {
  input('scenario', 'road_closure');
  input('seed', '33');
  input('demand_scale', '1.25');
  assert.equal(get('status').className, 'ok');
  assert.deepEqual(JSON.parse(get('preview').textContent), {
    scenario: 'road_closure', controller: 'max_pressure', seed: 33, demand_scale: 1.25, ev_preemption: true, duration_s: null, schema_version: 1,
  });
  assert.equal(get('command_file').textContent, 'teamb sandbox run sandbox_trial.json');
  assert.equal(get('command').textContent, `teamb exp run --name sandbox_trial --scenarios road_closure --controllers max_pressure --seeds 33 --ev-preemption on --scenario-params '{"demand_scale": 1.25}'`);
});

test('an empty seed is an error, not seed 0', () => {
  input('seed', '');
  assert.equal(get('status').className, 'error');
  assert.match(get('status').textContent, /Seed is required/);
  assert.equal(get('command').textContent, '');
  input('seed', '33');
  assert.equal(get('status').className, 'ok');
});

test('durations under 1200 s are rejected (900 s warm-up + 300 s measured)', () => {
  input('duration_s', '600');
  assert.equal(get('status').className, 'error');
  assert.match(get('status').textContent, /1200 and 10800/);
  input('duration_s', '1200');
  assert.equal(get('status').className, 'ok');
  assert.match(get('command').textContent, / --end 1200$/);
});

test('with storage blocked the live launch still navigates, from t = 0 and without coverage', () => {
  get('live_url').value = 'https://live-sumo.example';
  get('launch_live').click();
  assert.equal(get('status').className, 'ok', get('status').textContent);
  assert.equal(assigned.length, 1);
  const url = new URL(assigned[0]);
  assert.equal(url.origin, 'https://live-sumo.example');
  assert.equal(url.searchParams.get('start'), '0');
  assert.equal(url.searchParams.get('end'), '1200');
  assert.equal(url.searchParams.get('demand'), '1.25');
  assert.equal(url.searchParams.has('coverage'), false);
});

test('a GitHub Pages address or a plain http URL is refused', () => {
  get('live_url').value = 'https://team-b.github.io/repo/';
  get('launch_live').click();
  assert.match(get('status').textContent, /GitHub Pages cannot run SUMO/);
  get('live_url').value = 'http://live-sumo.example';
  get('launch_live').click();
  assert.match(get('status').textContent, /HTTPS/);
  get('live_url').value = '';
  get('launch_live').click();
  assert.match(get('status').textContent, /Enter the cloud simulator address/);
  assert.equal(assigned.length, 1);
});
