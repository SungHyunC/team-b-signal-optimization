// Run settings that arrive in the page URL (deep links, the Scenario Sandbox "Launch LIVE SUMO"
// button, the EN | 한국어 switch) and how they compare with the session that is already running.
// No DOM and no three.js here, so tests/js/launch.test.mjs runs it under node.
//
//   /?scenario=emergency&controller=coordinated&seed=1&coverage=0.25&start=1170&speed=2&ev=0
//     &demand=1.25&end=1200
//
// The hosted twin runs one simulation for every visitor. Opening or reloading a link must
// therefore only restart the run when the link asks for a different one (configDiffers).

/** URL keys that describe a run. Everything else (lang, camera, present, autostart) is view state. */
export const LAUNCH_KEYS = ['scenario', 'controller', 'seed', 'coverage', 'start', 'speed', 'ev', 'demand', 'end'];

/** Session settings from URL parameters (a URLSearchParams). */
export function urlConfig(params) {
  const cfg = {};
  if (params.get('scenario')) cfg.scenario = params.get('scenario');
  if (params.get('controller')) cfg.controller = params.get('controller');
  if (params.get('seed')) cfg.seed = Number(params.get('seed'));
  if (params.get('coverage')) {
    const c = Number(params.get('coverage'));
    cfg.coverage = c > 1 ? c / 100 : c; // accept 25 or 0.25
  }
  if (params.get('start')) cfg.start_at = Number(params.get('start'));
  if (params.get('speed')) cfg.speed = params.get('speed') === 'max' ? 'max' : Number(params.get('speed'));
  if (params.get('ev')) cfg.ev_preemption = params.get('ev') !== '0';
  if (params.has('demand')) cfg.scenario_params = { demand_scale: Number(params.get('demand')) };
  if (params.has('end')) cfg.end_time = Number(params.get('end'));
  return cfg;
}

/** Structural equality for JSON values: objects compare by content (in any key order), not by
 *  reference. The server sends config.scenario_params as a fresh object in every status. */
export function sameValue(a, b) {
  if (a === b) return true;
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  return ka.length === kb.length && kb.every((k) => Object.prototype.hasOwnProperty.call(a, k) && sameValue(a[k], b[k]));
}

/** True when the URL settings `want` ask for another run than `config` (the running session's
 *  config from /api/state). Speed and start time never force a restart. */
export function configDiffers(want, config) {
  if (!config) return false;
  return Object.entries(want).some(([k, v]) => k !== 'speed' && k !== 'start_at' && !sameValue(config[k], v));
}

/** The scenario's design coverage (e.g. 0.25 for fake_data_attack), or 1 when it has none. */
export function scenarioDefaultCoverage(meta, name) {
  const sc = ((meta && meta.scenarios) || []).find((s) => s.name === name);
  return sc && sc.defaults && sc.defaults.coverage != null ? sc.defaults.coverage : 1;
}

/** A start time at or after the end time would fast-forward straight to "finished": start at 0. */
export function withSafeStart(cfg) {
  if (cfg.end_time != null && Number(cfg.start_at) >= Number(cfg.end_time)) return { ...cfg, start_at: 0 };
  return cfg;
}

/** URL parameters that describe the run in `status` at the moment on screen, for the reload of
 *  the language switch. A null value removes a parameter left over from an earlier link, so the
 *  reloaded page asks for exactly the run that is running and does not restart it. */
export function stateParams(status, frame) {
  const s = status;
  if (!s || !s.config || !['running', 'paused', 'finished'].includes(s.state)) return {};
  const c = s.config;
  const demand = c.scenario_params ? c.scenario_params.demand_scale : null;
  return {
    scenario: c.scenario,
    controller: c.controller,
    seed: c.seed,
    start: s.state === 'finished' || !frame ? c.start_at : Math.floor(frame.t),
    speed: s.speed,
    coverage: c.coverage ?? null,
    ev: c.ev_preemption == null ? null : c.ev_preemption ? 1 : 0,
    demand: demand ?? null,
    end: c.end_time ?? null,
  };
}

/** `href` without the run parameters (keeps lang, camera, present, ...). */
export function stripLaunchParams(href) {
  const url = new URL(href);
  for (const k of LAUNCH_KEYS) url.searchParams.delete(k);
  return url.pathname + url.search + url.hash;
}
