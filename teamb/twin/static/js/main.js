// Entry point. Loads /api/meta and /api/geometry, builds the 3D scene and the panels, connects
// the WebSocket and routes its messages. Read this file first to see how the pieces fit:
//
//   server --hello/status/frame--> socket --> layers (vehicles, signals, overlays) + bus --> panels
//   panels --control/command--> socket --> server (runs them on the sim thread)
//
// URL parameters start a specific demo, e.g.
//   /?scenario=emergency&controller=coordinated&start=1170&speed=2&camera=J2&present=1
//
// The online demo (python -m teamb.twin.site) sets window.TWIN_STATIC: the same app then
// replays recorded runs (replay.js) instead of talking to a server.
window.__twinBooted = true; // the three.js imports resolved (see the fallback note in index.html)

import * as THREE from 'three';
import { api as liveApi, TwinSocket } from './net.js';
import { ReplaySocket, staticApi } from './replay.js';
import { addKo, controllerLabel, mountLanguageSwitch, scenarioTitle, t, translatePage } from './i18n.js';
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

// Korean for the static labels in index.html (data-i18n) and for this file.
addKo({
  'Signal Twin · Team B': 'Signal Twin · B팀',
  'Team B · 4-junction corridor': 'B팀 · 교차로 4개 구간',
  Scenario: '시나리오',
  Controller: '신호 제어 방식',
  Seed: '시드',
  'Start at': '시작 시점',
  'Start a new run with these settings': '이 설정으로 새로 실행해요',
  'Share of vehicles whose navigation app shares data (applies to vehicles departing from now on)':
    '내비 앱 데이터를 공유하는 차량의 비율 (지금부터 출발하는 차량에 적용돼요)',
  'Nav-app coverage': '내비 데이터 비율',
  'Give emergency vehicles a green path (signal preemption)': '긴급차량에 녹색 길을 열어 줘요 (우선 신호)',
  'EV priority': '긴급차량 우선',
  'Play / pause (Space)': '재생 / 일시정지 (Space)',
  'Advance one second (.)': '1초 앞으로 (.)',
  'Restart this run from the beginning': '이 실행을 처음부터 다시 시작',
  'not running': '실행 전',
  'Record the 3D view to a WebM video': '3D 화면을 WebM 영상으로 녹화',
  Record: '녹화',
  'Live twin': '실시간 트윈',
  Results: '실험 결과',
  'Connection to the twin server': '트윈 서버 연결 상태',
  connecting: '연결 중',
  'Click to jump to a time': '클릭하면 그 시점으로 이동해요',
  'Live KPIs': '실시간 지표',
  Signals: '신호',
  'click to fly there': '클릭하면 그 교차로로 이동',
  'Loading the 3D scene…': '3D 장면을 불러오는 중…',
  'Hide/show the left panel (P hides both)': '왼쪽 패널 숨기기/보이기 (P: 양쪽 모두)',
  'Hide/show the right panel (P hides both)': '오른쪽 패널 숨기기/보이기 (P: 양쪽 모두)',
  Actions: '직접 조작',
  'Event log': '이벤트 기록',
  'SPaT feed': 'SPaT 신호 정보',
  'what navigation apps receive': '내비 앱이 받는 정보',
  // video HUD (Record button)
  'Signal Twin · {scenario}': 'Signal Twin · {scenario}',
  'no run': '실행 없음',
  '{controller} · nav-app coverage {pct}% · Team B': '{controller} · 내비 데이터 비율 {pct}% · B팀',
  'warm-up': '워밍업',
  measuring: '측정 중',
  'Mean delay': '평균 지연',
  Vehicles: '차량',
  Halting: '정지 차량',
  'Mean speed': '평균 속도',
  'Could not start the twin: {error}': '트윈을 시작하지 못했어요: {error}',
});

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

const STATIC = window.TWIN_STATIC || null;

async function boot() {
  translatePage();
  const api = STATIC ? staticApi(STATIC.data) : liveApi;
  const [meta, geometry] = await Promise.all([api.get('/api/meta'), api.get('/api/geometry')]);
  const index = indexGeometry(geometry);
  const bus = new Bus();
  const socket = STATIC ? new ReplaySocket(meta, STATIC.data) : new TwinSocket();
  if (STATIC) api.player = socket;

  // --- 3D scene
  const view = createView($('#scene-host'), geometry);
  const roads = buildRoads(view.scene, geometry, index);
  buildCity(view.scene, geometry);
  const signals = new SignalLayer(view.scene, geometry, index);
  const vehicles = new VehicleLayer(view.scene);
  const ctx = {
    meta, geometry, index, api, socket, bus, view,
    static: STATIC, // set in the online demo: panels hide or explain what needs the live twin
    scene: view.scene,
    layers: { roads, signals, vehicles },
    state: { status: null, frame: null },
  };
  const overlays = OVERLAYS.map((Overlay) => new Overlay(ctx));
  ctx.layers.overlays = overlays;

  // --- EN | 한국어: the page reloads in the other language at the same run and moment
  mountLanguageSwitch($('#lang-switch'), () => {
    const s = ctx.state.status;
    const f = ctx.state.frame;
    if (!s || !s.config || !['running', 'paused', 'finished'].includes(s.state)) return {};
    const start = s.state === 'finished' || !f ? s.config.start_at : Math.floor(f.t);
    return { scenario: s.config.scenario, controller: s.config.controller, seed: s.config.seed, start, speed: s.speed };
  });

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
    let want = urlConfig(params);
    if (STATIC && !want.scenario) want = { ...meta.demo.default, ...want }; // the demo opens on its best moment
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
      title: t('Signal Twin · {scenario}', { scenario: sc ? scenarioTitle(sc) : t('no run') }),
      subtitle: t('{controller} · nav-app coverage {pct}% · Team B', { controller: ct ? controllerLabel(ct) : '–', pct: Math.round((f.coverage ?? 1) * 100) }),
      clock: fmtClock(f.t),
      phase: s.warmup != null && f.t < s.warmup ? t('warm-up') : t('measuring'),
      kpis: [
        [t('Mean delay'), `${fmtNum(k.mean_delay, 1)} s`],
        [t('Vehicles'), fmtNum(k.vehicles)],
        [t('Halting'), fmtNum(k.halting)],
        [t('Mean speed'), `${fmtNum((k.mean_speed ?? 0) * 3.6)} km/h`],
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
  const message = t('Could not start the twin: {error}', { error: err.message });
  const text = document.querySelector('.vp-overlay-text');
  if (text) text.textContent = message;
  toast(message, 'error', 10000);
});
