// replay.js (the online demo's player): the vehicle decoder against the Python encoder's
// output, and the playback state machine at the end of a recording and on download errors
// (frontend-4, frontend-5, frontend-12).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { decodeVehicles, ReplaySocket } from '../../teamb/twin/static/js/replay.js';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/vehicles.json', import.meta.url), 'utf8'));

test('decodeVehicles undoes teamb.twin.site.encode_vehicles', () => {
  let prev = new Map();
  for (const [n, frame] of fixture.frames.entries()) {
    const out = decodeVehicles(frame.flat, fixture.ids, fixture.kinds, prev);
    assert.deepEqual(out.vehicles, frame.vehicles, `frame ${n}`);
    prev = out.prev;
  }
});

// --- a tiny recording: 0..10 s in two chunks ----------------------------------------------
const BASE = 'data/';
const RUN = {
  id: 'r', end_t: 10, chunk_s: 5,
  chunks: [{ t0: 0, t1: 4, file: '000.json' }, { t0: 5, t1: 10, file: '001.json' }],
  ids: [], kinds: [],
  events: [{ t: 3, type: 'note' }],
  kpi_history: [{ t: 0 }, { t: 5 }, { t: 10 }],
  scenario: 'emergency', frame_controller: 'max_pressure', recorded: 'test',
  status: { config: { scenario: 'emergency', controller: 'max_pressure', seed: 1 }, step_length: 1, end_time: 10, summary: { mean_delay_s: 12.5 } },
};
const frames = (from, to) => Array.from({ length: to - from + 1 }, (_, k) => ({ t: from + k, v: [], ...(from + k === 3 ? { events: [{ t: 3, type: 'note' }] } : {}) }));
const META = { demo: { runs: [{ id: 'r', scenario: 'emergency', controller: 'max_pressure' }], default: { scenario: 'emergency', controller: 'max_pressure' } } };

function setup(overrides = {}) {
  const files = {
    [`${BASE}runs/r/run.json`]: RUN,
    [`${BASE}runs/r/000.json`]: { t0: 0, frames: frames(0, 4) },
    [`${BASE}runs/r/001.json`]: { t0: 5, frames: frames(5, 10) },
    ...overrides,
  };
  globalThis.fetch = async (url) => {
    const body = files[url];
    if (body === undefined || typeof body === 'number') return { ok: false, status: body ?? 404, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => structuredClone(body) };
  };
  const socket = new ReplaySocket(META, BASE);
  const clock = { ms: 0 };
  socket.now = () => clock.ms;
  const statuses = [];
  socket.on('status', (s) => statuses.push(s));
  socket.on('hello', (m) => statuses.push(m.status));
  const shown = [];
  socket.on('frame', (f) => shown.push(f.t));
  return { socket, clock, statuses, shown, files };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

/** Advance the wall clock by `ms` and let the player catch up (a chunk download in between
 *  holds the picture and restarts the clock from there, as in the browser). */
async function play(ctx, ms) {
  ctx.clock.ms += ms;
  for (let k = 0; k < 3; k++) {
    ctx.socket.tick();
    await settle();
  }
}

/** Keep the wall clock moving until playback stops (finished, error, paused). */
async function playToEnd(ctx) {
  for (let k = 0; k < 20 && ctx.socket.state === 'running'; k++) await play(ctx, 60000);
}

function done(ctx) {
  ctx.socket.stopClock(); // no interval may outlive the test
}

test('playing through the recording ends in "finished" with the clock stopped', async () => {
  const ctx = setup();
  try {
    await ctx.socket.start({ scenario: 'emergency', controller: 'max_pressure', start_at: 0, speed: 2 });
    assert.equal(ctx.socket.state, 'running');
    await play(ctx, 1000);
    assert.equal(ctx.socket.t, 2);
    await playToEnd(ctx);
    assert.equal(ctx.socket.t, 10);
    assert.equal(ctx.socket.state, 'finished');
    assert.equal(ctx.socket.playing, false);
    assert.equal(ctx.socket.timer, null);
    const last = ctx.statuses.at(-1);
    assert.equal(last.state, 'finished');
    assert.equal(last.summary.mean_delay_s, 12.5);
  } finally {
    done(ctx);
  }
});

test('jumping to the very end while playing finishes instead of hanging in "running"', async () => {
  const ctx = setup();
  try {
    await ctx.socket.start({ start_at: 0 });
    const r = await ctx.socket.control('jump', { t: 10 });
    assert.equal(r.ok, true);
    assert.equal(ctx.socket.state, 'finished');
    assert.equal(ctx.socket.timer, null);
    assert.equal(ctx.statuses.at(-1).summary.mean_delay_s, 12.5);
  } finally {
    done(ctx);
  }
});

test('play at the end (paused there, or after step on a finished run) replays from the start', async () => {
  const ctx = setup();
  try {
    await ctx.socket.start({ start_at: 0, autoplay: false });
    await ctx.socket.control('jump', { t: 10 }); // paused at the end
    assert.equal(ctx.socket.state, 'paused');
    await ctx.socket.control('play');
    assert.equal(ctx.socket.state, 'running');
    assert.equal(ctx.socket.t, 0);

    await playToEnd(ctx);
    assert.equal(ctx.socket.state, 'finished');
    await ctx.socket.control('step'); // '.' after the end: no-op
    assert.equal(ctx.socket.state, 'finished');
    await ctx.socket.control('play');
    assert.equal(ctx.socket.state, 'running');
    assert.equal(ctx.socket.t, 0);
    assert.ok(ctx.socket.timer);
  } finally {
    done(ctx);
  }
});

test('the clock never keeps running at the last frame', async () => {
  const ctx = setup();
  try {
    await ctx.socket.start({ start_at: 0, autoplay: false });
    await ctx.socket.control('jump', { t: 10 });
    ctx.socket.resume(); // whatever path gets here, the next tick finishes
    ctx.socket.tick();
    assert.equal(ctx.socket.state, 'finished');
    assert.equal(ctx.socket.timer, null);
  } finally {
    done(ctx);
  }
});

test('a recording whose first part fails to download shows an error, and Try again recovers', async () => {
  const ctx = setup({ [`${BASE}runs/r/000.json`]: 503 });
  try {
    await assert.rejects(ctx.socket.start({ start_at: 0 }), /503/);
    assert.equal(ctx.socket.state, 'error');
    assert.match(ctx.socket.error, /000\.json: 503/);
    assert.equal(ctx.statuses.at(-1).state, 'error');
    assert.ok(ctx.statuses.at(-1).error);
    ctx.files[`${BASE}runs/r/000.json`] = { t0: 0, frames: frames(0, 4) };
    const r = await ctx.socket.control('play'); // the overlay's "Try again"
    assert.equal(r.ok, true);
    assert.equal(ctx.socket.state, 'running');
    assert.equal(ctx.socket.error, null);
  } finally {
    done(ctx);
  }
});

test('a download failure during playback is shown as an error, not a silent pause', async () => {
  const ctx = setup({ [`${BASE}runs/r/001.json`]: 503 });
  try {
    await ctx.socket.start({ start_at: 0, speed: 2 });
    await play(ctx, 2600); // needs chunk 1 (t >= 5)
    assert.equal(ctx.socket.state, 'error');
    assert.equal(ctx.socket.playing, false);
    assert.equal(ctx.socket.timer, null);
    assert.match(ctx.statuses.at(-1).error, /next part of the recording/);
    const at = ctx.socket.t;
    ctx.files[`${BASE}runs/r/001.json`] = { t0: 5, frames: frames(5, 10) };
    await ctx.socket.control('play');
    assert.equal(ctx.socket.state, 'running');
    assert.equal(ctx.socket.t, at); // carries on where it stopped
    await playToEnd(ctx);
    assert.equal(ctx.socket.state, 'finished');
  } finally {
    done(ctx);
  }
});

test('a failed jump resolves with an error instead of rejecting', async () => {
  const ctx = setup({ [`${BASE}runs/r/001.json`]: 503 });
  try {
    await ctx.socket.start({ start_at: 0, autoplay: false });
    const r = await ctx.socket.control('jump', { t: 7 });
    assert.equal(r.ok, false);
    assert.match(r.error, /001\.json: 503/);
    assert.equal(ctx.socket.state, 'error');
    const step = await ctx.socket.control('step');
    assert.equal(step.ok, true); // stepping inside the loaded part still works
  } finally {
    done(ctx);
  }
});
