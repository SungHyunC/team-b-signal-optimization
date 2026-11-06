// sandbox_schema.js: the browser validator agrees with teamb/sandbox.py (shared fixture),
// contract 5 limits, the schema endpoint with its static fallback, the launch URL and the two
// CLI commands (frontend-2, frontend-7, frontend-12, frontend-13). test_frontend_js.py checks
// the built-in lists against teamb/sandbox.py (integration-13).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  DEFAULTS,
  EXPORT_FILE,
  experimentCommand,
  FALLBACK_SCHEMA,
  HEADLESS_CONTROLLER_PARAMS,
  launchParams,
  launchUrl,
  loadSchema,
  nonIntegerFields,
  normalizeSchema,
  parseImport,
  pyJsonDumps,
  sandboxRunCommand,
  shellQuote,
  validate,
} from '../../teamb/twin/static/js/sandbox_schema.js';
import { configDiffers, urlConfig } from '../../teamb/twin/static/js/launch.js';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/sandbox_cases.json', import.meta.url), 'utf8'));

test('every shared fixture case gets the same verdict as parse_sandbox_config', () => {
  for (const c of fixture.cases) {
    let verdict = true;
    let why = '';
    try {
      parseImport(c.text);
    } catch (err) {
      verdict = false;
      why = err.message;
      assert.equal(err.name, 'ConfigError', `${c.name}: ${err.stack}`);
    }
    assert.equal(verdict, c.ok, `${c.name}: ${why || 'accepted'}`);
  }
});

test('the equivalent teamb exp run command matches teamb.sandbox.experiment_command', () => {
  for (const c of fixture.commands) assert.equal(experimentCommand(validate(c.config)), c.exp_run);
  assert.equal(sandboxRunCommand(), 'teamb sandbox run sandbox_trial.json');
  assert.equal(EXPORT_FILE, 'sandbox_trial.json');
  assert.equal(experimentCommand(DEFAULTS).includes('--coverages'), false); // the scenario default coverage
});

test('a headless ai_recommender run auto-approves its plan, as teamb sandbox run does', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(HEADLESS_CONTROLLER_PARAMS)), { ai_recommender: { auto_approve: true } });
  const cmd = experimentCommand(validate({ controller: 'ai_recommender' }));
  assert.ok(cmd.endsWith(` --controller-params '{"ai_recommender": {"auto_approve": true}}'`), cmd);
  assert.equal(experimentCommand(DEFAULTS).includes('--controller-params'), false); // max_pressure needs none
});

test('pyJsonDumps writes what Python json.dumps writes (the run name hashes that text)', () => {
  assert.equal(pyJsonDumps({ a: { b: true, c: null }, d: [1, 2.5, 'x'] }), '{"a": {"b": true, "c": null}, "d": [1, 2.5, "x"]}');
  assert.equal(pyJsonDumps({ demand_scale: 1 }), '{"demand_scale": 1}');
  assert.equal(pyJsonDumps('caf\u00e9 \u{1F6A6} "q"\n\u007f'), '"caf\\u00e9 \\ud83d\\udea6 \\"q\\"\\n\\u007f"');
  assert.equal(pyJsonDumps({}), '{}');
  assert.equal(pyJsonDumps([]), '[]');
});

test('contract 5: duration is blank or 1200-10800 s; the schema matches the endpoint shape', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(FALLBACK_SCHEMA.limits)), { seed: [0, 2147483647], demand_scale: [0.1, 3.0], duration_s: [1200, 10800] });
  assert.equal(FALLBACK_SCHEMA.schema_version, 1);
  for (const ok of [null, 1200, 3600, 10800]) assert.equal(validate({ duration_s: ok }).duration_s, ok);
  for (const bad of [60, 300, 1199, 10801, 1800.5, '1800', true]) assert.throws(() => validate({ duration_s: bad }), /Duration/, String(bad));
});

test('missing fields take the SandboxConfig defaults; validate returns the complete config', () => {
  assert.deepEqual(validate({}), { ...DEFAULTS });
  assert.deepEqual(validate({ seed: 9 }), { ...DEFAULTS, seed: 9 });
  assert.throws(() => validate({ seed: 9, color: 'red' }), /Unsupported field: color/);
  assert.throws(() => validate(null), /Expected a JSON object/);
});

test('integer fields written with a fraction or exponent are found in the raw text', () => {
  assert.deepEqual(nonIntegerFields('{"seed": 5.0, "duration_s": 1.2e3, "schema_version": 1}'), ['seed', 'duration_s']);
  assert.deepEqual(nonIntegerFields('{"seed": 5, "demand_scale": 1.0, "schema_version":1}'), []);
  assert.deepEqual(nonIntegerFields('{"schema_version":1.}'), ['schema_version']);
});

test('a server schema replaces the lists and limits; a broken one is ignored', () => {
  const server = { schema_version: 1, scenarios: ['rush_hour'], controllers: ['max_pressure', 'max_pressure_spillback'], limits: { seed: [0, 99], demand_scale: [0.5, 2], duration_s: [1200, 7200] } };
  const s = normalizeSchema(server);
  assert.deepEqual(s, server);
  assert.equal(validate({ controller: 'max_pressure_spillback' }, s).controller, 'max_pressure_spillback');
  assert.throws(() => validate({ seed: 100 }, s), /between 0 and 99/);
  assert.throws(() => validate({ duration_s: 9000 }, s), /1200 and 7200/);
  assert.deepEqual(normalizeSchema({ ...server, limits: undefined }).limits, JSON.parse(JSON.stringify(FALLBACK_SCHEMA.limits)));
  for (const broken of [null, [], { ...server, schema_version: 2 }, { ...server, scenarios: [] }, { ...server, controllers: ['ok', 'rm -rf /'] }, { ...server, scenarios: 'rush_hour' }]) {
    assert.equal(normalizeSchema(broken), null, JSON.stringify(broken));
  }
  assert.deepEqual(normalizeSchema({ ...server, limits: { seed: [5, 1], demand_scale: ['a', 2] } }).limits.seed, [0, 2147483647]);
});

test('loadSchema: the twin endpoint when it answers, the built-in lists otherwise', async () => {
  const good = { schema_version: 1, scenarios: ['rush_hour'], controllers: ['fixed_time'], limits: { seed: [0, 10], demand_scale: [0.1, 3], duration_s: [1200, 10800] } };
  const asked = [];
  const reply = (status, body) => async (url) => {
    asked.push(url);
    return { ok: status === 200, status, json: async () => (body instanceof Error ? Promise.reject(body) : body) };
  };
  let r = await loadSchema({ fetch: reply(200, good) });
  assert.equal(r.source, 'server');
  assert.deepEqual(r.schema.controllers, ['fixed_time']);
  assert.equal(asked.at(-1), '../api/sandbox/schema'); // relative: /api/sandbox/schema from /static/sandbox.html
  for (const f of [reply(404, {}), reply(401, { detail: 'login required' }), reply(200, new SyntaxError('html')), reply(200, { schema_version: 9 }), async () => { throw new TypeError('offline'); }]) {
    r = await loadSchema({ fetch: f });
    assert.equal(r.source, 'built-in');
    assert.equal(r.schema, FALLBACK_SCHEMA);
  }
  const before = asked.length;
  r = await loadSchema({ fetch: reply(200, good), skip: true }); // static GitHub Pages: no request
  assert.equal(r.source, 'built-in');
  assert.equal(asked.length, before);
  r = await loadSchema({ fetch: (url, opts) => new Promise((_, reject) => opts.signal.addEventListener('abort', () => reject(new Error('aborted')))), timeoutMs: 10 });
  assert.equal(r.source, 'built-in');
});

test('the live launch URL runs the exported config from t = 0 with the scenario coverage', () => {
  const cfg = validate({ scenario: 'road_closure', seed: 33, demand_scale: 1.25, ev_preemption: false, duration_s: 1800 });
  assert.deepEqual(launchParams(cfg), { scenario: 'road_closure', controller: 'max_pressure', seed: 33, demand: 1.25, ev: 0, start: 0, speed: 2, end: 1800 });
  assert.equal('end' in launchParams(validate({})), false);
  assert.equal('coverage' in launchParams(cfg), false);
  const href = launchUrl('https://live.example', cfg);
  assert.equal(href, 'https://live.example/?scenario=road_closure&controller=max_pressure&seed=33&demand=1.25&ev=0&start=0&speed=2&end=1800');
  // The twin maps it back to the session it posts, and a reload of the same link attaches.
  const want = urlConfig(new URL(href).searchParams);
  assert.deepEqual(want, { scenario: 'road_closure', controller: 'max_pressure', seed: 33, start_at: 0, speed: 2, ev_preemption: false, scenario_params: { demand_scale: 1.25 }, end_time: 1800 });
  const running = JSON.parse(JSON.stringify({ ...want, coverage: null, start_at: 0, speed: '2', controller_params: {}, sampling: 'uniform', autoplay: true }));
  assert.equal(configDiffers(want, running), false);
  assert.equal(configDiffers(urlConfig(new URL(href).searchParams), running), false);
});

test('shellQuote quotes like Python shlex.quote', () => {
  assert.equal(shellQuote('sandbox_trial'), 'sandbox_trial');
  assert.equal(shellQuote('{"demand_scale": 1}'), `'{"demand_scale": 1}'`);
  assert.equal(shellQuote("it's"), `'it'"'"'s'`);
  assert.equal(shellQuote(''), "''");
});
