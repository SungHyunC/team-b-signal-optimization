// recorder.js HUD: browsers without CanvasRenderingContext2D.roundRect (Chrome < 99,
// Firefox < 112) get square panels instead of an exception in the render loop (ext-187).
import test from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

import { FakeElement, installDom } from './support/fake_dom.mjs';

register('./support/three_loader.mjs', import.meta.url);
installDom();
const { Recorder } = await import('../../teamb/twin/static/js/recorder.js');

/** A 2D context that records the calls made on it; `roundRect` only when asked for. */
function context2d({ roundRect }) {
  const calls = [];
  const g = new Proxy(
    { calls },
    {
      get(target, key) {
        if (key in target) return target[key];
        if (key === 'roundRect' && !roundRect) return undefined;
        if (key === 'measureText') return (text) => ({ width: String(text).length * 7 });
        return (...args) => calls.push([key, ...args]);
      },
      set: () => true,
    },
  );
  return g;
}

const hud = () => ({
  title: 'Signal Twin · Rush hour', subtitle: 'Max pressure · nav-app coverage 100% · Team B', clock: '12:34', phase: 'measuring',
  kpis: [['Mean delay', '31.8 s'], ['Vehicles', '210']], event: '12:00  Ambulance dispatched',
});

test('the HUD falls back to plain rectangles without roundRect', () => {
  const rec = new Recorder({ onAfterRender() {} }, new FakeElement('button'), hud);
  const g = context2d({ roundRect: false });
  assert.doesNotThrow(() => rec.drawHud(g, 1920, 1080));
  const names = g.calls.map((c) => c[0]);
  assert.equal(names.filter((n) => n === 'rect').length, 4); // title, clock, KPIs, event panels
  assert.ok(names.includes('fillText'));
});

test('browsers with roundRect keep the rounded panels', () => {
  const rec = new Recorder({ onAfterRender() {} }, new FakeElement('button'), hud);
  const g = context2d({ roundRect: true });
  rec.drawHud(g, 1280, 720);
  const names = g.calls.map((c) => c[0]);
  assert.equal(names.filter((n) => n === 'roundRect').length, 4);
  assert.equal(names.includes('rect'), false);
});
