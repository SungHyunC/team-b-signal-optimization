// Talking to the twin server: small REST helpers and a WebSocket that reconnects by itself.
//
// Server -> browser messages: hello, frame, status, reply (see teamb/twin/server.py).
// Browser -> server: {type: 'control', action, speed, t} and {type: 'command', command: {...}}.
// command()/control() return a Promise that resolves with the server's reply.

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
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.connected = true;
      this.retry = 500;
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
    ws.onclose = () => {
      const was = this.connected;
      this.connected = false;
      if (this.ws === ws) this.ws = null;
      for (const p of this.pending.values()) {
        clearTimeout(p.timer);
        p.resolve({ ok: false, error: 'connection lost' });
      }
      this.pending.clear();
      if (was) this.emit('close');
      setTimeout(() => this.connect(), this.retry);
      this.retry = Math.min(this.retry * 1.7, 5000);
    };
    ws.onerror = () => ws.close();
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
