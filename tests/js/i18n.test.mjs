// i18n.js: language detection must not accept inherited Object.prototype keys (ext-177).
// Each test file runs in its own process, so the globals below only affect this file.
import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = { search: '?lang=constructor' };
const store = new Map([['twin.lang', '__proto__']]);
globalThis.localStorage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };

const i18n = await import('../../teamb/twin/static/js/i18n.js');

test('prototype keys are not languages', () => {
  for (const code of ['constructor', '__proto__', 'toString', 'hasOwnProperty', '', null, undefined, 1]) {
    assert.equal(i18n.isLang(code), false, String(code));
  }
  assert.equal(i18n.isLang('en'), true);
  assert.equal(i18n.isLang('ko'), true);
});

test('?lang=constructor and a tampered saved choice fall back to the browser language', () => {
  assert.ok(['en', 'ko'].includes(i18n.lang), i18n.lang);
});

test('t() never returns an inherited property', () => {
  i18n.addKo({ Start: '시작' });
  assert.equal(i18n.t('constructor'), 'constructor');
  assert.equal(i18n.t('toString'), 'toString');
  assert.equal(i18n.t('Hello {name}', { name: 'B' }), 'Hello B');
});
