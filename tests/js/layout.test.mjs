// Phone layout (twin.css, max-width 640px): the AI card must not cover the event banners
// (FAKE DATA SUSPECTED, closures, EV priority) or the collapsed legend (frontend-9).
// A static check of the stylesheet; there is no browser in this test run.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const STATIC = new URL('../../teamb/twin/static/', import.meta.url);
const css = readFileSync(new URL('css/twin.css', STATIC), 'utf8');
const html = readFileSync(new URL('index.html', STATIC), 'utf8');

/** selector -> {property: value} for the rules inside `@media (max-width: 640px) { ... }`. */
function phoneRules() {
  const start = css.indexOf('@media (max-width: 640px)');
  assert.ok(start >= 0);
  const body = css.slice(css.indexOf('{', start) + 1, css.indexOf('\n}', start));
  const rules = {};
  for (const m of body.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    const decls = Object.fromEntries(m[2].split(';').map((d) => d.split(':').map((x) => x.trim())).filter((d) => d[0]).map(([k, ...v]) => [k, v.join(':')]));
    for (const sel of m[1].split(',').map((x) => x.trim())) rules[sel] = { ...(rules[sel] || {}), ...decls };
  }
  return rules;
}
const px = (v) => Number(String(v).replace('px', ''));

test('title and banners share one box at the top of the view', () => {
  assert.match(html, /<div class="vp-top">[\s\S]*?id="vp-title"[\s\S]*?id="banners"[\s\S]*?<\/div>\s*<\/div>/);
  assert.match(css, /\.vp-top \{ display: contents; \}/); // desktop layout unchanged
  const r = phoneRules();
  assert.equal(r['.vp-top'].position, 'absolute');
  assert.equal(px(r['.vp-top'].top), 8);
  assert.equal(r['.vp-top .vp-banners'].position, 'static');
  assert.equal(r['.vp-banners'] && r['.vp-banners'].bottom, undefined, 'banners must not be anchored at the bottom next to the AI card');
});

test('the AI card sits above the collapsed legend and the camera bar', () => {
  const r = phoneRules();
  assert.equal(r['.ai-card'].top, 'auto');
  const legendBottom = px(r['.legend'].bottom);
  assert.ok(px(r['.ai-card'].bottom) >= legendBottom + 30, `ai-card bottom ${r['.ai-card'].bottom} vs legend ${r['.legend'].bottom}`);
  assert.ok(px(r['.camera-bar'].bottom) < legendBottom);
  assert.equal(r['.legend:not(.collapsed)']['z-index'], '4'); // an opened legend goes over the card
});
