// Tiny DOM helpers, an event bus and toasts shared by the UI panels.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** h('div', {class: 'x', onclick: fn}, 'text', childNode, ...) -> HTMLElement */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'html') el.innerHTML = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

/** Fill a <select> with [{value, label}] and keep the current value if it still exists. */
export function fillSelect(select, options, value) {
  const keep = value ?? select.value;
  select.innerHTML = '';
  for (const o of options) select.append(h('option', { value: o.value, title: o.title || null }, o.label));
  if (options.some((o) => String(o.value) === String(keep))) select.value = keep;
}

/** Publish/subscribe between modules: bus.on('frame', fn); bus.emit('frame', data). */
export class Bus {
  constructor() {
    this.handlers = new Map();
  }
  on(type, fn) {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type).push(fn);
  }
  emit(type, data) {
    for (const fn of this.handlers.get(type) || []) {
      try {
        fn(data);
      } catch (err) {
        console.error(`bus '${type}' handler failed`, err);
      }
    }
  }
}

export function toast(text, kind = 'info', ms = 3800) {
  const host = document.getElementById('toasts');
  if (!host) return;
  const el = h('div', { class: `toast ${kind}` }, text);
  host.append(el);
  setTimeout(() => el.remove(), ms);
}
