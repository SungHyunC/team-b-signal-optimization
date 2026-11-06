// results.js: a report section shows every scalar column. The shipped reports' estimation
// section has 17, and the last three (est_flow_mae, est_flow_bias, false_alarm_s) used to be
// cut off without notice (ext-195).
import test from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { readdirSync, readFileSync, existsSync } from 'node:fs';

import { installDom } from './support/fake_dom.mjs';

register('./support/three_loader.mjs', import.meta.url);
installDom();
const { ResultsView } = await import('../../teamb/twin/static/js/results.js');

const META = { scenarios: [{ name: 'fake_data_attack', title: 'Fake data attack' }], controllers: [{ name: 'max_pressure', label: 'Max pressure' }] };

function headers(card) {
  // card = details > [summary, div > table > tr(th...), tr(td...)...]
  const table = card.children[1].children[0];
  return table.children[0].children.map((th) => th.textContent);
}

test('a section with more than 14 columns shows all of them', () => {
  const view = new ResultsView({ meta: META });
  const row = Object.fromEntries(Array.from({ length: 17 }, (_, i) => [`col_${i}`, i]));
  row.est_flow_mae = { mean: 1.5, ci95: 0.2 };
  const card = view.section('Estimation', [row, { ...row, col_0: 99 }], {});
  assert.equal(headers(card).length, 18);
  assert.equal(card.children[1].children[0].children.length, 3); // header + 2 rows
});

test('the shipped estimation sections show all their columns (est_flow_mae, est_flow_bias, false_alarm_s)', () => {
  const dir = new URL('../../docs/results/reports/', import.meta.url);
  if (!existsSync(dir)) return; // docs not part of this checkout
  const scalar = (v) => v === null || ['number', 'string', 'boolean'].includes(typeof v) || (typeof v === 'object' && 'mean' in v);
  let widest = 0;
  for (const name of readdirSync(dir)) {
    const file = new URL(`${name}/report.json`, dir);
    if (!existsSync(file)) continue;
    const report = JSON.parse(readFileSync(file, 'utf8'));
    if (!Array.isArray(report.estimation) || !report.estimation.length) continue;
    const cols = new Set(report.estimation.flatMap((r) => Object.keys(r).filter((k) => scalar(r[k]))));
    const view = new ResultsView({ meta: META });
    assert.equal(headers(view.section('Estimation', report.estimation, report.definitions || {})).length, cols.size, name);
    widest = Math.max(widest, cols.size);
  }
  assert.ok(widest >= 17, `widest estimation section has ${widest} columns`);
});
