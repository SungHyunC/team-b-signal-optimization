// Scenario Sandbox schema, validation, launch URL and CLI commands. No DOM here: the page
// (sandbox.js) and tests/js/sandbox_schema.test.mjs both import it.
//
// Keep it aligned with teamb/sandbox.py (parse_sandbox_config, experiment_command): the same
// cases in tests/js/fixtures/sandbox_cases.json are run through both validators.
//
// Served by the twin, the page reads the lists and limits from GET /api/sandbox/schema:
//   {"schema_version": 1, "scenarios": [...], "controllers": [...],
//    "limits": {"seed": [0, 2147483647], "demand_scale": [0.1, 3.0], "duration_s": [1200, 10800]}}
// On static GitHub Pages there is no server and FALLBACK_SCHEMA is used.

export const SCHEMA_VERSION = 1;
export const WARMUP_S = 900; // every scenario warms up 900 s before measuring (hence duration >= 1200)
export const EXPORT_FILE = 'sandbox_trial.json';
export const MAX_IMPORT_BYTES = 100000;

export const FALLBACK_SCHEMA = Object.freeze({
  schema_version: SCHEMA_VERSION,
  scenarios: Object.freeze(['rush_hour', 'off_peak', 'special_event', 'emergency', 'road_closure', 'sinkhole_cross', 'earthquake', 'fake_data_attack']),
  controllers: Object.freeze(['fixed_time', 'coordinated', 'actuated', 'max_pressure', 'max_pressure_plus', 'max_pressure_probe', 'ai_recommender', 'rl']),
  limits: Object.freeze({ seed: Object.freeze([0, 2147483647]), demand_scale: Object.freeze([0.1, 3.0]), duration_s: Object.freeze([1200, 10800]) }),
});

/** SandboxConfig defaults in teamb/sandbox.py: a missing field means this value. */
export const DEFAULTS = Object.freeze({
  scenario: 'rush_hour',
  controller: 'max_pressure',
  seed: 1,
  demand_scale: 1,
  ev_preemption: true,
  duration_s: null,
  schema_version: SCHEMA_VERSION,
});
export const FIELDS = Object.freeze(Object.keys(DEFAULTS));
/** Fields Python requires to be JSON integers (5, not 5.0 or 5e0). */
const INTEGER_FIELDS = ['seed', 'duration_s', 'schema_version'];

const fill = (text, vars) => text.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? String(vars[k]) : m));

/** A validation error; `key` + `vars` let the page translate it (t(key, vars)). */
export class ConfigError extends Error {
  constructor(key, vars = {}) {
    super(fill(key, vars));
    this.name = 'ConfigError';
    this.key = key;
    this.vars = vars;
  }
}

const isPlainObject = (v) => !!v && typeof v === 'object' && !Array.isArray(v);
const NAME = /^[A-Za-z0-9_.-]+$/; // registry names: safe in an <option> and on a command line

/** A schema from the server, checked; null when it is not usable (the page then keeps FALLBACK_SCHEMA). */
export function normalizeSchema(raw) {
  const names = (a) => Array.isArray(a) && a.length > 0 && a.every((x) => typeof x === 'string' && NAME.test(x));
  const pair = (p) => Array.isArray(p) && p.length === 2 && p.every((x) => typeof x === 'number' && Number.isFinite(x)) && p[0] <= p[1];
  if (!isPlainObject(raw) || raw.schema_version !== SCHEMA_VERSION || !names(raw.scenarios) || !names(raw.controllers)) return null;
  const limits = {};
  for (const [k, fallback] of Object.entries(FALLBACK_SCHEMA.limits)) {
    const given = isPlainObject(raw.limits) ? raw.limits[k] : null;
    limits[k] = pair(given) ? [given[0], given[1]] : [...fallback];
  }
  return { schema_version: SCHEMA_VERSION, scenarios: [...raw.scenarios], controllers: [...raw.controllers], limits };
}

/** GET the server's schema; FALLBACK_SCHEMA on static hosting (skip), on any error or timeout. */
export async function loadSchema({ fetch: get = globalThis.fetch, url = '../api/sandbox/schema', skip = false, timeoutMs = 4000 } = {}) {
  const builtIn = { schema: FALLBACK_SCHEMA, source: 'built-in' };
  if (skip || typeof get !== 'function') return builtIn;
  const abort = typeof AbortController === 'function' ? new AbortController() : null;
  const timer = abort ? setTimeout(() => abort.abort(), timeoutMs) : null;
  try {
    const r = await get(url, { cache: 'no-store', credentials: 'same-origin', headers: { Accept: 'application/json' }, signal: abort ? abort.signal : undefined });
    if (!r || !r.ok) return builtIn;
    const schema = normalizeSchema(await r.json());
    return schema ? { schema, source: 'server' } : builtIn;
  } catch {
    return builtIn;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/** Check a configuration like parse_sandbox_config: unknown fields are rejected, missing ones
 *  take the defaults. Returns the complete configuration; throws ConfigError. */
export function validate(v, schema = FALLBACK_SCHEMA) {
  if (!isPlainObject(v)) throw new ConfigError('Expected a JSON object');
  const unknown = Object.keys(v).filter((k) => !FIELDS.includes(k));
  if (unknown.length) throw new ConfigError('Unsupported field: {field}', { field: unknown.sort().join(', ') });
  const c = { ...DEFAULTS, ...v };
  const { limits } = schema;
  if (c.schema_version !== SCHEMA_VERSION) throw new ConfigError('Unsupported schema version');
  if (!schema.scenarios.includes(c.scenario)) throw new ConfigError('Unknown scenario: {name}', { name: String(c.scenario) });
  if (!schema.controllers.includes(c.controller)) throw new ConfigError('Unknown controller: {name}', { name: String(c.controller) });
  const [seedMin, seedMax] = limits.seed;
  if (!Number.isInteger(c.seed) || c.seed < seedMin || c.seed > seedMax) throw new ConfigError('Seed must be an integer between {min} and {max}', { min: seedMin, max: seedMax });
  const [dMin, dMax] = limits.demand_scale;
  if (typeof c.demand_scale !== 'number' || !Number.isFinite(c.demand_scale) || c.demand_scale < dMin || c.demand_scale > dMax) {
    throw new ConfigError('Demand multiplier must be between {min} and {max}', { min: dMin, max: dMax });
  }
  if (typeof c.ev_preemption !== 'boolean') throw new ConfigError('EMS preemption must be true or false');
  const [tMin, tMax] = limits.duration_s;
  if (c.duration_s !== null && (!Number.isInteger(c.duration_s) || c.duration_s < tMin || c.duration_s > tMax)) {
    throw new ConfigError('Duration must be blank or a whole number of seconds between {min} and {max}', { min: tMin, max: tMax });
  }
  return c;
}

/** Integer fields written as 5.0 or 5e0 in the JSON text. JSON.parse cannot tell them from 5,
 *  but Python reads them as floats and rejects them, so the browser must reject them too. */
export function nonIntegerFields(text) {
  const out = [];
  const re = new RegExp(`"(${INTEGER_FIELDS.join('|')})"\\s*:\\s*(-?\\d+(?:\\.\\d*)?(?:[eE][+-]?\\d+)?)`, 'g');
  for (const m of String(text).matchAll(re)) if (/[.eE]/.test(m[2]) && !out.includes(m[1])) out.push(m[1]);
  return out;
}

/** An imported file's text -> the complete, validated configuration (throws ConfigError). */
export function parseImport(text, schema = FALLBACK_SCHEMA) {
  if (String(text).length > MAX_IMPORT_BYTES) throw new ConfigError('File too large');
  let value;
  try {
    value = JSON.parse(text);
  } catch (err) {
    throw new ConfigError('Not valid JSON: {error}', { error: err.message });
  }
  if (!isPlainObject(value)) throw new ConfigError('Expected a JSON object');
  const floats = nonIntegerFields(text);
  if (floats.length) throw new ConfigError('{field} must be a whole number (write 5, not 5.0)', { field: floats[0] });
  return validate(value, schema);
}

/** Query parameters of the live twin for this run (read by launch.js urlConfig). No coverage:
 *  the twin uses the scenario's own, like the CLI commands. start=0: run from the beginning,
 *  as the commands do (the twin's form would otherwise start at 4:00). */
export function launchParams(cfg) {
  const params = {
    scenario: cfg.scenario,
    controller: cfg.controller,
    seed: cfg.seed,
    demand: cfg.demand_scale,
    ev: cfg.ev_preemption ? 1 : 0,
    start: 0,
    speed: 2,
  };
  if (cfg.duration_s != null) params.end = cfg.duration_s;
  return params;
}

export function launchUrl(origin, cfg) {
  const url = new URL('/', origin);
  for (const [k, v] of Object.entries(launchParams(cfg))) url.searchParams.set(k, String(v));
  return url.href;
}

/** shlex.quote: leave safe words alone, single-quote the rest. */
export function shellQuote(word) {
  const s = String(word);
  if (s && /^[A-Za-z0-9_@%+=:,./-]+$/.test(s)) return s;
  return `'${s.replace(/'/g, `'"'"'`)}'`;
}

/** The `teamb exp run` command for this configuration (teamb.sandbox.experiment_command). */
export function experimentCommand(cfg, name = 'sandbox_trial') {
  const parts = [
    'teamb', 'exp', 'run', '--name', name,
    '--scenarios', cfg.scenario,
    '--controllers', cfg.controller,
    '--seeds', String(cfg.seed),
    '--ev-preemption', cfg.ev_preemption ? 'on' : 'off',
    '--scenario-params', `{"demand_scale": ${JSON.stringify(cfg.demand_scale)}}`,
  ];
  if (cfg.duration_s != null) parts.push('--end', String(cfg.duration_s));
  return parts.map(shellQuote).join(' ');
}

/** Run an exported file (teamb.sandbox main: validate, simulate, write a report). */
export function sandboxRunCommand(file = EXPORT_FILE) {
  return `teamb sandbox run ${shellQuote(file)}`;
}
