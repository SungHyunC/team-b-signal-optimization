// Talking to the twin server: small REST helpers and a WebSocket that reconnects by itself.
//
// Server -> browser messages: hello, frame, status, reply (see teamb/twin/server.py).
// Browser -> server: {type: 'control', action, speed, t} and {type: 'command', command: {...}}.
// command()/control() return a Promise that resolves with the server's reply.
//
// On an access-gated deployment the login cookie expires after 12 h; the server then refuses
// the WebSocket. TwinSocket notices (close code 1008, or a few failed connects in a row), asks
// GET /api/state, and on 401 sends the browser to /login?next=<this page> instead of
// "reconnecting…" forever.

const LOGIN_CHECK_EVERY = 3; // failed connects in a row before asking whether the login expired

/** The login page, coming back to this page (path and query) afterwards. */
export function loginUrl(loc = location) {
  return `/login?next=${encodeURIComponent(loc.pathname + loc.search)}`;
}

export const api = {
  async get(path) {
    const r = await fetch(path, { cache: 'no-store' });
    if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || `${path}: ${r.status}`);
    return data;
  },
};

export class TwinSocket {
  constructor(url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`) {
    this.url = url;
    this.handlers = new Map();
    this.pending = new Map(); // message id -> {resolve, timer}
    this.nextId = 1;
    this.retry = 500;
    this.connected = false;
    this.ws = null;
    this.failures = 0; // connects in a row that never opened
    this.stopped = false; // leaving for the login page
    this.checkingLogin = false;
  }

  /** on('frame' | 'status' | 'hello' | 'reply' | 'open' | 'close', fn) */
  on(type, fn) {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type).push(fn);
    return this;
  }

  emit(type, data) {
    for (const fn of this.handlers.get(type) || []) {
      try {
        fn(data);
      } catch (err) {
        console.error(`handler for '${type}' failed`, err);
      }
    }
  }

  connect() {
    if (this.stopped) return;
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.connected = true;
      this.retry = 500;
      this.failures = 0;
      this.emit('open');
    };
    ws.onmessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === 'reply' && msg.id != null && this.pending.has(msg.id)) {
        const p = this.pending.get(msg.id);
        clearTimeout(p.timer);
        this.pending.delete(msg.id);
        p.resolve(msg);
      }
      this.emit(msg.type, msg);
    };
    ws.onclose = (ev) => {
      const was = this.connected;
      this.connected = false;
      if (this.ws === ws) this.ws = null;
      for (const p of this.pending.values()) {
        clearTimeout(p.timer);
        p.resolve({ ok: false, error: 'connection lost' });
      }
      this.pending.clear();
      if (was) this.emit('close');
      else this.failures += 1;
      // 1008 = "login required"; browsers may report 1006 instead, hence the count as well.
      if ((ev && ev.code === 1008) || (this.failures && this.failures % LOGIN_CHECK_EVERY === 0)) this.checkLogin();
      setTimeout(() => this.connect(), this.retry);
      this.retry = Math.min(this.retry * 1.7, 5000);
    };
    ws.onerror = () => ws.close();
  }

  /** GET /api/state answers 401 when the login cookie is missing or expired: go and log in. */
  async checkLogin() {
    if (this.checkingLogin || this.stopped) return;
    this.checkingLogin = true;
    try {
      const r = await fetch('/api/state', { cache: 'no-store', credentials: 'same-origin' });
      if (r.status === 401) {
        this.stopped = true;
        location.assign(loginUrl());
      }
    } catch {
      // server unreachable: keep reconnecting
    } finally {
      this.checkingLogin = false;
    }
  }

  send(msg, timeoutMs = 15000) {
    return new Promise((resolve) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        resolve({ ok: false, error: 'not connected to the twin server' });
        return;
      }
      const id = this.nextId++;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        resolve({ ok: false, error: 'no reply from the server' });
      }, timeoutMs);
      this.pending.set(id, { resolve, timer });
      this.ws.send(JSON.stringify({ ...msg, id }));
    });
  }

  control(action, extra = {}) {
    return this.send({ type: 'control', action, ...extra }, 120000);
  }

  command(command) {
    return this.send({ type: 'command', command });
  }
}
