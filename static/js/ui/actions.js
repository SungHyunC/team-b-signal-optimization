// Actions panel: dispatch an emergency vehicle, close/reopen a road (also by clicking a road in
// the 3D view), start/stop the fake navigation-data attack. Every action is a SimEnv command
// sent over the WebSocket (see "Commands" in docs/ARCHITECTURE.md).
import { addKo, lang, t } from '../i18n.js';
import { APPROACH_NAMES, fmtClock, vehicleLabel } from '../util.js';
import { $, fillSelect, h, toast } from './dom.js';

addKo({
  'Online demo: these controls need the live twin. Clone the repo and run {cmd}.':
    '온라인 데모예요. 이 조작은 실시간 트윈에서만 돼요. 저장소를 클론하고 {cmd} 명령을 실행하세요.',
  'Vehicle type': '차량 종류',
  Route: '경로',
  Dispatch: '출동',
  'Emergency vehicle': '긴급차량',
  'follow with the camera': '카메라로 따라가기',
  'Road (edge)': '도로 (구간)',
  Cause: '원인',
  'Close road': '도로 폐쇄',
  Reopen: '재개통',
  'Road closure (disaster)': '도로 폐쇄 (재난)',
  'both directions': '양방향',
  'Tip: click any road in the 3D view to close or reopen it.': '팁: 3D 화면에서 도로를 클릭하면 폐쇄하거나 재개통할 수 있어요.',
  'Where the phantom phones claim a queue': '가짜 휴대폰이 대기열을 거짓 보고할 위치',
  'Number of phantom phones': '가짜 휴대폰 수',
  'Like the 2020 Berlin "99 phones" stunt: phones report a jam that is not there.':
    '2020년 베를린 "휴대폰 99대" 실험처럼, 휴대폰들이 있지도 않은 정체를 보고해요.',
  'Fake navigation data': '가짜 내비 데이터',
  'Start attack': '공격 시작',
  Stop: '중지',
  '{junction} · {approach} approach': '{junction} · {approach} 진입로',
  'command failed': '명령이 실패했어요',
  'no simulation running': '실행 중인 시뮬레이션이 없어요',
  Vehicle: '차량',
  '{vehicle} dispatched: {route}': '{vehicle} 출동했어요: {route}',
  '{edge} (both directions)': '{edge} 양방향',
  'Road {edge} closed ({cause})': '{edge} 도로를 폐쇄했어요 ({cause})',
  '{n} vehicles rerouted': '차량 {n}대 경로 변경',
  'Road {edge} reopened': '{edge} 도로를 재개통했어요',
  'Fake-data attack started: {n} phantom phones at {junction} {approach}':
    '가짜 데이터 공격을 시작했어요: {junction} {approach} 진입로에 가짜 휴대폰 {n}대',
  'Fake-data attack stopped': '가짜 데이터 공격을 멈췄어요',
  'Closed at {time} ({cause}).': '{time}에 폐쇄됐어요 ({cause}).',
  'Detour: {route}.': '우회 경로: {route}.',
  'Click to reopen.': '클릭하면 재개통해요.',
  '{edge} · reopen': '{edge} · 재개통',
  'attack running': '공격 중',
  '{n} phones at {junction} {approach} since {time}': '{time}부터 {junction} {approach} 진입로에 가짜 휴대폰 {n}대',
  'cross-check caught it': '교차검증으로 감지됨',
  'not flagged yet': '아직 감지 안 됨',
  'No attack running.': '진행 중인 공격이 없어요.',
  'This is an entry/exit road at the edge of the network. Closing it would block traffic from entering, so it is not offered.':
    '도로망 가장자리의 진입·진출 도로예요. 막으면 차량이 들어오지 못해서 폐쇄할 수 없어요.',
  'Closed since {time} ({cause}).': '{time}부터 폐쇄 중이에요 ({cause}).',
  'Reopen road': '도로 재개통',
  'Close this road? Vehicles that planned to use it are rerouted.': '이 도로를 폐쇄할까요? 이 도로를 지나려던 차량은 경로를 바꿔요.',
});

// The selects show the server's English labels (ctx.meta). In Korean they are rebuilt from the
// ids and fields, and an approach letter (N) becomes its word (북쪽).
const ko = lang === 'ko';
const ROUTES_KO = {
  eb_arterial: '동쪽 방향 간선도로',
  wb_arterial: '서쪽 방향 간선도로',
  nb_j2: 'J2 경유 북쪽 방향',
  sb_j3: 'J3 경유 남쪽 방향',
  s4_west: 'S4 출발, 간선도로 서쪽 방향',
};
const side = (a) => (ko ? t(APPROACH_NAMES[a] || a) : a);
const routeLabel = (r) =>
  ko && ROUTES_KO[r.id] ? `${ROUTES_KO[r.id]} (${r.origin.split('_')[0]} → ${r.destination.split('_').pop()})` : r.label;
const targetLabel = (x) => (ko ? t('{junction} · {approach} approach', { junction: x.junction, approach: side(x.approach) }) : x.label);
const edgeLabel = (e) => (ko ? `${e.from} → ${e.to} · ${t(e.kind)}, ${t(e.direction)}` : e.label);

export class ActionsPanel {
  constructor(ctx) {
    this.ctx = ctx;
    this.closures = [];
    this.attack = null;
    const { meta } = ctx;
    const root = $('#actions');
    if (ctx.static) {
      const [before, after] = t('Online demo: these controls need the live twin. Clone the repo and run {cmd}.').split('{cmd}');
      root.append(h('div', { class: 'demo-note' }, before, h('code', {}, 'python -m teamb twin'), after));
    }

    // --- emergency vehicle
    this.evKind = h('select', { title: t('Vehicle type') });
    fillSelect(this.evKind, meta.ev_kinds.map((k) => ({ value: k.id, label: t(k.label) })));
    this.evRoute = h('select', { title: t('Route') });
    fillSelect(this.evRoute, meta.emergency_routes.map((r) => ({ value: r.id, label: routeLabel(r) })));
    this.evFollow = h('input', { type: 'checkbox', checked: true });
    const dispatch = h('button', { class: 'btn small bad', onclick: () => this.dispatch() }, t('Dispatch'));
    root.append(
      h('div', { class: 'act' },
        h('div', { class: 'act-title' }, h('span', { class: 'sw round', style: { background: '#ff4d4d' } }), t('Emergency vehicle')),
        h('div', { class: 'act-row' }, this.evKind, this.evRoute),
        h('div', { class: 'act-row' }, h('label', { class: 'act-check' }, this.evFollow, t('follow with the camera')), h('span', { style: { flex: 1 } }), dispatch),
      ),
    );

    // --- road closure
    this.edge = h('select', { title: t('Road (edge)') });
    fillSelect(this.edge, meta.closable_edges.map((e) => ({ value: e.id, label: edgeLabel(e) })), 'J2_J3');
    this.cause = h('select', { title: t('Cause') });
    fillSelect(this.cause, meta.closure_causes.map((c) => ({ value: c.id, label: t(c.label) })));
    this.closedList = h('div', { class: 'act-list' });
    this.bothDirs = h('input', { type: 'checkbox' });
    root.append(
      h('div', { class: 'act' },
        h('div', { class: 'act-title' }, h('span', { class: 'sw', style: { background: '#3b82c4' } }), t('Road closure (disaster)')),
        h('div', { class: 'act-row' }, this.edge),
        h('div', { class: 'act-row' }, this.cause,
          // t('Close') is the overlay's 닫기 (viewport.js), so in Korean this button says 도로 폐쇄.
          h('button', { class: 'btn small warn', onclick: () => this.closeRoad(this.edge.value, this.cause.value, this.bothDirs.checked) }, ko ? t('Close road') : 'Close'),
          h('button', { class: 'btn small', onclick: () => this.reopenRoad(this.edge.value, this.bothDirs.checked) }, t('Reopen'))),
        h('div', { class: 'act-row' }, h('label', { class: 'act-check' }, this.bothDirs, t('both directions'))),
        this.closedList,
        h('div', { class: 'act-note' }, t('Tip: click any road in the 3D view to close or reopen it.')),
      ),
    );

    // --- fake-data attack
    this.target = h('select', { title: t('Where the phantom phones claim a queue') });
    fillSelect(this.target, meta.attack_targets.map((x) => ({ value: `${x.junction}:${x.approach}`, label: targetLabel(x) })));
    this.phones = h('input', { type: 'number', min: 1, max: 500, value: 99, title: t('Number of phantom phones') });
    this.attackStatus = h('div', { class: 'act-note' }, t('Like the 2020 Berlin "99 phones" stunt: phones report a jam that is not there.'));
    root.append(
      h('div', { class: 'act' },
        h('div', { class: 'act-title' }, h('span', { class: 'sw', style: { background: '#a855f7' } }), t('Fake navigation data')),
        h('div', { class: 'act-row' }, this.target, this.phones),
        h('div', { class: 'act-row' },
          h('button', { class: 'btn small purple', onclick: () => this.startAttack() }, t('Start attack')),
          h('button', { class: 'btn small', onclick: () => this.stopAttack() }, t('Stop'))),
        this.attackStatus,
      ),
    );

    this.menu = $('#road-menu');
    document.addEventListener('pointerdown', (e) => {
      if (!this.menu.hidden && !this.menu.contains(e.target)) this.menu.hidden = true;
    });
    ctx.bus.on('frame', (f) => this.onFrame(f));
    ctx.bus.on('road-click', ({ edge, x, y }) => this.showRoadMenu(edge, x, y));
  }

  async send(command, okText) {
    const r = await this.ctx.socket.command(command);
    if (r.ok === false) toast(t(r.error || 'command failed'), r.demo ? 'info' : 'error', 6000);
    else if (okText) toast(typeof okText === 'function' ? okText(r) : okText, 'ok');
    return r;
  }

  async dispatch() {
    const route = this.ctx.meta.emergency_routes.find((r) => r.id === this.evRoute.value);
    if (!route) return;
    const r = await this.send(
      { type: 'dispatch_ev', origin: route.origin, destination: route.destination, kind: this.evKind.value },
      (reply) => t('{vehicle} dispatched: {route}', { vehicle: vehicleLabel(reply.result) || t('Vehicle'), route: routeLabel(route) }),
    );
    if (r.ok !== false && r.result && this.evFollow.checked) this.ctx.camera.followVehicle(r.result);
  }

  closeRoad(edge, cause, bothDirections = false) {
    const what = bothDirections ? t('{edge} (both directions)', { edge }) : edge;
    return this.send({ type: 'close_road', edge, cause, both_directions: bothDirections }, (r) => {
      const res = r.result || {};
      const text = t('Road {edge} closed ({cause})', { edge: what, cause: t(cause) });
      return res.rerouted != null ? `${text} · ${t('{n} vehicles rerouted', { n: res.rerouted })}` : text;
    });
  }

  reopenRoad(edge, bothDirections = false) {
    const what = bothDirections ? t('{edge} (both directions)', { edge }) : edge;
    return this.send({ type: 'reopen_road', edge, both_directions: bothDirections }, t('Road {edge} reopened', { edge: what }));
  }

  startAttack() {
    const [junction, approach] = this.target.value.split(':');
    const n = Math.max(1, Math.min(500, Number(this.phones.value) || 99));
    return this.send(
      { type: 'start_attack', junction, approach, n },
      t('Fake-data attack started: {n} phantom phones at {junction} {approach}', { n, junction, approach: side(approach) }),
    );
  }

  stopAttack() {
    return this.send({ type: 'stop_attack' }, t('Fake-data attack stopped'));
  }

  onFrame(f) {
    const closures = f.closures || [];
    const key = closures.map((c) => c.edge).join(',');
    if (key !== this._closureKey) {
      this._closureKey = key;
      this.closures = closures;
      this.closedList.innerHTML = '';
      for (const c of closures) {
        const detour = Array.isArray(c.detour) && c.detour.length ? ` ${t('Detour: {route}.', { route: c.detour.join(' → ') })}` : '';
        const title = `${t('Closed at {time} ({cause}).', { time: fmtClock(c.since), cause: t(c.cause) })}${detour} ${t('Click to reopen.')}`;
        this.closedList.append(
          h('button', { class: 'btn small', title, onclick: () => this.reopenRoad(c.edge) }, t('{edge} · reopen', { edge: c.edge })),
        );
      }
    }
    const a = f.attack;
    const alerts = (f.alerts || []).filter((x) => x.type === 'probe_detector_mismatch');
    if (a) {
      this.attackStatus.innerHTML = '';
      this.attackStatus.append(
        h('span', { class: 'badge purple' }, t('attack running')),
        ` ${t('{n} phones at {junction} {approach} since {time}', { n: a.n, junction: a.junction, approach: side(a.approach), time: fmtClock(a.since) })} · `,
        alerts.length ? h('span', { class: 'badge green' }, t('cross-check caught it')) : h('span', { class: 'badge yellow' }, t('not flagged yet')),
      );
    } else if (this.attack) {
      this.attackStatus.textContent = t('No attack running.');
    }
    this.attack = a;
  }

  showRoadMenu(edgeId, x, y) {
    const { meta } = this.ctx;
    const edge = meta.closable_edges.find((e) => e.id === edgeId);
    const closed = this.closures.find((c) => c.edge === edgeId);
    const m = this.menu;
    m.innerHTML = '';
    m.append(h('div', { class: 'pt' }, edge ? edgeLabel(edge) : edgeId));
    if (!edge) {
      m.append(h('div', { class: 'ps' }, t('This is an entry/exit road at the edge of the network. Closing it would block traffic from entering, so it is not offered.')));
    } else if (closed) {
      m.append(
        h('div', { class: 'ps' }, t('Closed since {time} ({cause}).', { time: fmtClock(closed.since), cause: t(closed.cause) })),
        h('div', { class: 'row' }, h('button', { class: 'btn small good', onclick: () => { this.reopenRoad(edgeId); m.hidden = true; } }, t('Reopen road'))),
      );
    } else {
      const cause = h('select');
      fillSelect(cause, meta.closure_causes.map((c) => ({ value: c.id, label: t(c.label) })));
      const both = h('input', { type: 'checkbox' });
      m.append(
        h('div', { class: 'ps' }, t('Close this road? Vehicles that planned to use it are rerouted.')),
        h('div', { class: 'row' }, cause, h('button', { class: 'btn small warn', onclick: () => { this.closeRoad(edgeId, cause.value, both.checked); m.hidden = true; } }, t('Close road'))),
        h('label', { class: 'act-check' }, both, t('both directions')),
      );
    }
    m.hidden = false;
    const host = m.parentElement.getBoundingClientRect();
    const w = m.offsetWidth;
    const hh = m.offsetHeight;
    m.style.left = `${Math.min(Math.max(8, x - host.left + 12), host.width - w - 8)}px`;
    m.style.top = `${Math.min(Math.max(8, y - host.top + 12), host.height - hh - 8)}px`;
  }
}
