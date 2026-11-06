// The Korean lookup: a null-prototype dictionary, so 'constructor' is never "translated".
import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = { search: '?lang=ko' };
const i18n = await import('../../teamb/twin/static/js/i18n.js');

test('?lang=ko selects Korean', () => {
  assert.equal(i18n.lang, 'ko');
});

test('registered strings translate, unknown and inherited keys stay English', () => {
  i18n.addKo({ 'Starting {scenario}…': '{scenario} 시작 중…' });
  assert.equal(i18n.t('Starting {scenario}…', { scenario: 'rush_hour' }), 'rush_hour 시작 중…');
  assert.equal(i18n.t('not translated'), 'not translated');
  assert.equal(i18n.t('constructor'), 'constructor');
  assert.equal(i18n.t('__proto__'), '__proto__');
});
