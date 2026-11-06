// Every visible top-bar text and tooltip in index.html is marked for translation (data-i18n /
// data-i18n-title) and has Korean registered in a module (frontend-11).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';

const STATIC = new URL('../../teamb/twin/static/', import.meta.url);
const html = readFileSync(new URL('index.html', STATIC), 'utf8');
const js = ['js/', 'js/ui/'].flatMap((dir) => readdirSync(new URL(dir, STATIC)).filter((f) => f.endsWith('.js')).map((f) => readFileSync(new URL(dir + f, STATIC), 'utf8'))).join('\n');
const registered = (text) => js.includes(`'${text}':`) || js.includes(`"${text}":`) || js.includes(`  ${text}:`);
const topbar = html.slice(html.indexOf('<header id="topbar">'), html.indexOf('</header>'));

test('top-bar links, buttons and tooltips are tagged for translation', () => {
  for (const m of topbar.matchAll(/<(a|button|span|div)\b([^>]*)>([^<]+)</g)) {
    const [, tag, attrs, text] = m;
    const label = text.trim();
    // (btn-apply's label is set by TopBar.markDirty with t(); the brand name stays as is)
    if (!label || /^[-–:%0-9]+$/.test(label) || label === 'Signal Twin' || /id="(f-coverage-val|clock-time|btn-apply)"/.test(attrs)) continue;
    assert.match(attrs, /data-i18n(?!-)/, `<${tag}> "${label}" has no data-i18n`);
  }
  for (const m of topbar.matchAll(/<(\w+)\b([^>]*\btitle="([^"]+)"[^>]*)>/g)) {
    const [, tag, attrs, title] = m;
    if (attrs.includes('class="brand"')) continue; // team credit, same in both languages
    assert.match(attrs, /data-i18n-title/, `<${tag}> title "${title}" has no data-i18n-title`);
  }
});

test('every data-i18n text and title in index.html has Korean registered', () => {
  const missing = [];
  for (const m of html.matchAll(/<\w+\b[^>]*\bdata-i18n(?!-)[^>]*>([^<]+)</g)) if (!registered(m[1].trim())) missing.push(m[1].trim());
  for (const m of html.matchAll(/<\w+\b([^>]*)>/g)) {
    if (!/data-i18n-title/.test(m[1])) continue;
    const title = m[1].match(/\btitle="([^"]+)"/)[1];
    if (!registered(title)) missing.push(title);
  }
  assert.deepEqual(missing, []);
});
