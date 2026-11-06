// kpis.js throughput tile: the label names the window the rate really covers; early in a run
// that is less than 5 minutes (ext-202).
import test from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

import { installDom } from './support/fake_dom.mjs';

register('./support/three_loader.mjs', import.meta.url);
installDom();
const { throughput, throughputText } = await import('../../teamb/twin/static/js/ui/kpis.js');

/** KPI samples every 5 sim-s from t0 to t1 with `perMin` arrivals per minute. */
const samples = (t0, t1, perMin) => Array.from({ length: (t1 - t0) / 5 + 1 }, (_, i) => ({ t: t0 + 5 * i, arrived: ((5 * i) / 60) * perMin }));

test('no rate until 30 s of history', () => {
  assert.equal(throughput(samples(0, 30, 10)), null);
  assert.equal(throughputText(null), 'throughput: collecting…');
});

test('a short history is labelled with its real window', () => {
  const tp = throughput(samples(0, 60, 10));
  assert.equal(tp.window, 60);
  assert.equal(Math.round(tp.rate), 600);
  assert.equal(throughputText(tp), 'throughput ≈ 600 veh/h (last 60 s)');
  assert.equal(throughputText(throughput(samples(0, 180, 10))), 'throughput ≈ 600 veh/h (last 3 min)');
});

test('with five minutes or more it is the last 5 minutes', () => {
  const tp = throughput(samples(0, 900, 10));
  assert.equal(tp.window, 300);
  assert.equal(throughputText(tp), 'throughput ≈ 600 veh/h (last 5 min)');
});
