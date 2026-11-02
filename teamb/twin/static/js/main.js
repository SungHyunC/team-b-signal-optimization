// Entry point. Loads /api/meta and /api/geometry, builds the 3D scene and the panels, connects
// the WebSocket and routes its messages. Read this file first to see how the pieces fit:
//
//   server --hello/status/frame--> socket --> layers (vehicles, signals, overlays) + bus --> panels
//   panels --control/command--> socket --> server (runs them on the sim thread)
//
// URL parameters start a specific demo, e.g.
//   /?scenario=emergency&controller=coordinated&start=1170&speed=2&camera=J2&present=1
window.__twinBooted = true; // the three.js imports resolved (see the fallback note in index.html)

import * as THREE from 'three';
import { api, TwinSocket } from './net.js';
import { createView } from './scene.js';
import { buildRoads } from './roads.js';
import { buildCity } from './city.js';
import { SignalLayer } from './signals.js';
import { VehicleLayer } from './vehicles.js';
import { OVERLAYS } from './overlays.js';
import { Recorder } from './recorder.js';
import { ResultsView } from './results.js';
import { fmtClock, fmtNum, indexGeometry } from './util.js';
import { $, Bus, toast } from './ui/dom.js';
import { TopBar } from './ui/topbar.js';
import { KpiPanel } from './ui/kpis.js';
import { JunctionPanel } from './ui/junctions.js';
import { describeEvent, EventLog } from './ui/events.js';
import { ActionsPanel } from './ui/actions.js';
import { AiCard } from './ui/ai.js';
import { SpatPanel } from './ui/spat.js';
import { CameraControl, ViewportChrome } from './ui/viewport.js';

/** Session settings from the URL (?scenario=...&controller=...&seed=...&coverage=0.25&start=1170&speed=5&ev=0). */
function urlConfig(params) {
  const cfg = {};
  if (params.get('scenario')) cfg.scenario = params.get('scenario');
  if (params.get('controller')) cfg.controller = params.get('controller');
  if (params.get('seed')) cfg.seed = Number(params.get('seed'));
  if (params.get('coverage')) {
    const c = Number(params.get('coverage'));
    cfg.coverage = c > 1 ? c / 100 : c; // accept 25 or 0.25
  }
  if (params.get('start')) cfg.start_at = Number(params.get('start'));
  if (params.get('speed')) cfg.speed = params.get('speed') === 'max' ? 'max' : Number(params.get('speed'));
  if (params.get('ev')) cfg.ev_preemption = params.get('ev') !== '0';
  return cfg;
}

async function boot() {
  const [meta, geometry] = await Promise.all([api.get('/api/meta'), api.get('/api/geometry')]);
  const index = indexGeometry(geometry);
  const bus = new Bus();
  const socket = new TwinSocket();

  // --- 3D scene
  const view = createView($('#scene-host'), geometry);
  const roads = buildRoads(view.scene, geometry, index);
  buildCity(view.scene, geometry);
  const signals = new SignalLayer(view.scene, geometry, index);
  const vehicles = new VehicleLayer(view.scene);
  const ctx = {
    meta, geometry, index, api, socket, bus, view,
    scene: view.scene,
    layers: { roads, signals, vehicles },
    state: { status: null, frame: null },
  };
  const overlays = OVERLAYS.map((Overlay) => new Overlay(ctx));
  ctx.layers.overlays = overlays;

  // --- panels (each subscribes to the bus itself)
  ctx.camera = new CameraControl(ctx);
  ctx.topbar = new TopBar(ctx);
  const chrome = new ViewportChrome(ctx);
  new KpiPanel(ctx);
  new JunctionPanel(ctx);
  new EventLog(ctx);
  new ActionsPanel(ctx);
  new AiCard(ctx);
  new SpatPanel(ctx);
  const results = new ResultsView(ctx);

  view.onFrame((now, dt) => {
    vehicles.update(now, view.viewDistance());
    for (const o of overlays) if (o.animate) o.animate(now, dt);
  });

  // --- messages from the server
  let lastEvent = null;
  let autostartDone = false;
  const params = new URLSearchParams(location.search);

  function onStatus(s) {
    const prev = ctx.state.status;
    ctx.state.status = s;
    if (!prev || prev.sid !== s.sid) {
      // A new session: start from an empty road.
      vehicles.clear();
      for (const o of overlays) if (o.reset) o.reset();
      lastEvent = null;
      if (prev) bus.emit('session', s);
    }
    bus.emit('status', s);
    if (!autostartDone) {
      autostartDone = true;
      autostart(s);
    }
  }

  function autostart(s) {
    // Open the page -> something is moving. A URL config restarts the run if it differs.
    if (params.get('autostart') === '0') return;
    const want = urlConfig(params);
    const differs = s.config && Object.entries(want).some(([k, v]) => k !== 'speed' && k !== 'start_at' && s.config[k] !== v);
    if (Object.keys(want).length) ctx.topbar.setForm(want);
    if (['idle', 'error', 'finished'].includes(s.state) || differs) ctx.topbar.start(want);
    else if (want.speed != null && String(want.speed) !== String(s.speed)) ctx.topbar.setSpeed(want.speed);
  }

  socket.on('open', () => bus.emit('connection', true));
  socket.on('close', () => bus.emit('connection', false));
  socket.on('hello', (msg) => {
    onStatus(msg.status);
    bus.emit('hello', msg);
  });
  socket.on('status', (s) => onStatus(s));
  socket.on('frame', (f) => {
    const s = ctx.state.status;
    if (s && f.sid !== s.sid) return; // a late frame from the previous session
    ctx.state.frame = f;
    vehicles.applyFrame(f, performance.now());
    signals.update(f.signals);
    for (const o of overlays) o.update(f);
    for (const e of f.events || []) lastEvent = e;
    bus.emit('frame', f);
  });

  // --- click a road to close / reopen it (a click, not an orbit drag)
  const canvas = view.renderer.domElement;
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let down = null;
  canvas.addEventListener('pointerdown', (e) => (down = { x: e.clientX, y: e.clientY, t: performance.now() }));
  canvas.addEventListener('pointerup', (e) => {
    if (!down || e.button !== 0 || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5 || performance.now() - down.t > 500) return;
    const rect = canvas.getBoundingClientRect();
    ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, view.camera);
    const edge = roads.pickEdge(raycaster);
    if (edge) bus.emit('road-click', { edge, x: e.clientX, y: e.clientY });
  });

  // --- live / results tabs
  bus.on('view', (name) => {
    $('#live-view').hidden = name !== 'live';
    $('#timeline').hidden = name !== 'live';
    $('#results-view').hidden = name !== 'results';
    if (name === 'results') results.show();
  });

  // --- keyboard shortcuts for the presenter
  const live = $('#live-view');
  const presentation = () => {
    const hide = !(live.classList.contains('hide-left') && live.classList.contains('hide-right'));
    live.classList.toggle('hide-left', hide);
    live.classList.toggle('hide-right', hide);
  };
  window.addEventListener('keydown', (e) => {
    const target = e.target.closest ? e.target : document.body;
    if (target.closest('input, select, textarea') && e.key !== 'Escape') return; // typing in a field
    if (target.closest('button') && (e.key === ' ' || e.key === 'Enter')) return; // the button handles it
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const junction = meta.junctions[Number(e.key) - 1];
    if (e.key === ' ') {
      e.preventDefault();
      ctx.topbar.togglePlay();
    } else if (e.key === '.') ctx.topbar.step();
    else if (e.key === '0') ctx.camera.fly('overview');
    else if (junction) ctx.camera.fly(junction);
    else if (e.key === 't' || e.key === 'T') ctx.camera.fly('top');
    else if (e.key === 'f' || e.key === 'F') ctx.camera.followLatest();
    else if (e.key === 'p' || e.key === 'P') presentation();
    else if (e.key === 'Escape') $('#road-menu').hidden = true;
  });
  if (params.get('present') === '1') presentation();
  if (params.get('camera')) setTimeout(() => ctx.camera.fly(params.get('camera')), 300);

  // --- Record button: 3D view + a small HUD, saved as WebM
  new Recorder(view, $('#btn-record'), () => {
    const s = ctx.state.status || {};
    const f = ctx.state.frame || {};
    const k = f.kpi || {};
    const cfg = s.config || {};
    const sc = meta.scenarios.find((x) => x.name === cfg.scenario);
    const ct = meta.controllers.find((x) => x.name === cfg.controller);
    return {
      title: `Signal Twin · ${sc ? sc.title : 'no run'}`,
      subtitle: `${ct ? ct.label : '–'} · nav-app coverage ${Math.round((f.coverage ?? 1) * 100)}% · Team B`,
      clock: fmtClock(f.t),
      phase: s.warmup != null && f.t < s.warmup ? 'warm-up' : 'measuring',
      kpis: [
        ['Mean delay', `${fmtNum(k.mean_delay, 1)} s`],
        ['Vehicles', fmtNum(k.vehicles)],
        ['Halting', fmtNum(k.halting)],
        ['Mean speed', `${fmtNum((k.mean_speed ?? 0) * 3.6)} km/h`],
      ],
      event: lastEvent ? `${fmtClock(lastEvent.t)}  ${describeEvent(lastEvent).text}` : null,
    };
  });

  socket.connect();
  chrome.hideBootOverlay();
  window.twin = ctx; // handy in the browser console: twin.state.frame, twin.view.flyTo('J2'), ...
}

boot().catch((err) => {
  console.error(err);
  const text = document.querySelector('.vp-overlay-text');
  if (text) text.textContent = `Could not start the twin: ${err.message}`;
  toast(`Could not start the twin: ${err.message}`, 'error', 10000);
});
