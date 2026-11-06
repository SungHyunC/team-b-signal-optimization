// Just enough of the DOM for the UI panels under node: elements with children, attributes,
// classList, listeners, <select> value semantics and document.querySelector('#id').
// installDom() puts document/window/Node on globalThis; elements are created on first lookup.

export class FakeNode {}

class FakeText extends FakeNode {
  constructor(text) {
    super();
    this.text = String(text);
  }
  get textContent() {
    return this.text;
  }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this);
  }
}

class ClassList {
  constructor() {
    this.set = new Set();
  }
  add(...c) { c.forEach((x) => this.set.add(x)); }
  remove(...c) { c.forEach((x) => this.set.delete(x)); }
  contains(c) { return this.set.has(c); }
  toggle(c, force) {
    const on = force === undefined ? !this.set.has(c) : !!force;
    if (on) this.set.add(c);
    else this.set.delete(c);
    return on;
  }
}

export class FakeElement extends FakeNode {
  constructor(tag) {
    super();
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.style = {};
    this.listeners = {};
    this.classList = new ClassList();
    this.checked = false;
    this.disabled = false;
    this.hidden = false;
    this.title = '';
    this.parent = null;
    this._value = '';
    this._text = '';
    this._selected = undefined; // <select>: undefined = first option, null = none
    this._queries = new Map();
  }
  setAttribute(k, v) {
    this.attributes[k] = String(v);
    if (k === 'value') this._value = String(v);
    if (k === 'title') this.title = String(v);
    if (k.startsWith('data-')) this.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = String(v);
  }
  getAttribute(k) {
    return this.attributes[k] ?? null;
  }
  addEventListener(type, fn) {
    (this.listeners[type] ||= []).push(fn);
  }
  dispatch(type, extra = {}) {
    for (const fn of this.listeners[type] || []) fn({ type, target: this, preventDefault() {}, stopPropagation() {}, ...extra });
  }
  click() {
    this.dispatch('click');
  }
  append(...nodes) {
    for (let n of nodes) {
      if (!(n instanceof FakeNode)) n = new FakeText(n);
      n.parent = this;
      this.children.push(n);
    }
  }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this);
  }
  set innerHTML(_) {
    this.children = [];
    this._text = '';
    this._selected = undefined;
  }
  get innerHTML() {
    return this.textContent;
  }
  get textContent() {
    return this._text + this.children.map((c) => c.textContent).join('');
  }
  set textContent(v) {
    this.children = [];
    this._text = String(v);
  }
  get className() {
    return [...this.classList.set].join(' ');
  }
  set className(v) {
    this.classList.set = new Set(String(v).split(/\s+/).filter(Boolean));
  }
  get options() {
    return this.children.filter((c) => c.tagName === 'OPTION');
  }
  get value() {
    if (this.tagName !== 'SELECT') return this._value;
    const opts = this.options;
    if (this._selected === undefined) return opts.length ? opts[0]._value : '';
    return this._selected ?? '';
  }
  set value(v) {
    if (this.tagName !== 'SELECT') {
      this._value = String(v);
      return;
    }
    this._selected = this.options.some((o) => o._value === String(v)) ? String(v) : null;
  }
  closest() {
    return (this._closest ||= new FakeElement('label'));
  }
  querySelector(sel) {
    if (!this._queries.has(sel)) this._queries.set(sel, new FakeElement('div'));
    return this._queries.get(sel);
  }
  querySelectorAll() {
    return [];
  }
  getBoundingClientRect() {
    return { left: 0, top: 0, width: 100, height: 10 };
  }
  getContext() {
    return null;
  }
}

/** Elements that are <select> or <input> in index.html / sandbox.html. */
const SELECTS = new Set(['f-scenario', 'f-controller', 'f-start', 'scenario', 'controller']);

export function installDom() {
  const byId = new Map();
  const get = (id) => {
    if (!byId.has(id)) {
      const el = new FakeElement(SELECTS.has(id) ? 'select' : 'input');
      el.id = id;
      byId.set(id, el);
    }
    return byId.get(id);
  };
  const document = {
    title: '',
    documentElement: {},
    activeElement: null,
    createElement: (tag) => new FakeElement(tag),
    createTextNode: (text) => new FakeText(text),
    querySelector: (sel) => (sel.startsWith('#') ? get(sel.slice(1)) : null),
    querySelectorAll: () => [],
    getElementById: (id) => byId.get(id) || null, // toasts: no host, so toast() is a no-op
  };
  globalThis.document = document;
  globalThis.Node = FakeNode;
  globalThis.window = { matchMedia: () => ({ matches: false }) };
  globalThis.confirm = () => true;
  return { document, get };
}
