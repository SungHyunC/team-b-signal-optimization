// net.js TwinSocket: an expired login cookie on the access-gated twin leads to the login page
// instead of "reconnecting…" forever (frontend-10).
import test, { mock } from 'node:test';
import assert from 'node:assert/strict';

const assigned = [];
globalThis.location = { protocol: 'https:', host: 'twin.example', pathname: '/', search: '?lang=ko&camera=J2', assign: (u) => assigned.push(u) };

/** WebSockets that never open: the server closes them before accepting (with `code`). */
const sockets = [];
let closeCode = 1006;
class RefusedSocket {
  static OPEN = 1;
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    sockets.push(this);
    queueMicrotask(() => this.onclose && this.onclose({ code: closeCode }));
  }
  close() {}
}
globalThis.WebSocket = RefusedSocket;

let stateStatus = 401;
let probes = 0;
globalThis.fetch = async (url) => {
  probes += 1;
  assert.equal(url, '/api/state');
  return { status: stateStatus, ok: stateStatus === 200 };
};

const { loginUrl, TwinSocket } = await import('../../teamb/twin/static/js/net.js');
const settle = async () => {
  for (let k = 0; k < 5; k++) await new Promise((r) => setImmediate(r));
};

test('loginUrl comes back to this page with its query', () => {
  assert.equal(loginUrl({ pathname: '/', search: '?lang=ko&camera=J2' }), '/login?next=%2F%3Flang%3Dko%26camera%3DJ2');
});

test('a 1008 close with an expired cookie redirects to the login page and stops reconnecting', async (t) => {
  mock.timers.enable({ apis: ['setTimeout'] });
  t.after(() => mock.timers.reset());
  assigned.length = 0;
  sockets.length = 0;
  probes = 0;
  closeCode = 1008;
  stateStatus = 401;
  const s = new TwinSocket('wss://twin.example/ws');
  s.connect();
  await settle();
  assert.equal(probes, 1);
  assert.deepEqual(assigned, ['/login?next=%2F%3Flang%3Dko%26camera%3DJ2']);
  mock.timers.tick(10000);
  await settle();
  assert.equal(sockets.length, 1); // no new connection after leaving for the login page
});

test('without a close code it asks after a few failed connects', async (t) => {
  mock.timers.enable({ apis: ['setTimeout'] });
  t.after(() => mock.timers.reset());
  assigned.length = 0;
  sockets.length = 0;
  probes = 0;
  closeCode = 1006;
  stateStatus = 401;
  const s = new TwinSocket('wss://twin.example/ws');
  s.connect();
  for (let k = 0; k < 3 && !assigned.length; k++) {
    await settle();
    mock.timers.tick(5000);
  }
  await settle();
  assert.equal(probes, 1);
  assert.equal(sockets.length, 3);
  assert.equal(assigned.length, 1);
});

test('a server that is just down (no 401) keeps reconnecting', async (t) => {
  mock.timers.enable({ apis: ['setTimeout'] });
  t.after(() => mock.timers.reset());
  assigned.length = 0;
  sockets.length = 0;
  probes = 0;
  closeCode = 1006;
  stateStatus = 200;
  const s = new TwinSocket('wss://twin.example/ws');
  s.connect();
  for (let k = 0; k < 7; k++) {
    await settle();
    mock.timers.tick(5000);
  }
  await settle();
  assert.equal(assigned.length, 0);
  assert.ok(sockets.length >= 7);
  assert.equal(probes, 2); // after the 3rd and the 6th failure
  s.stopped = true; // end the loop
});
