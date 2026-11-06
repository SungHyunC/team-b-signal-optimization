// Everything drawn over the 3D view in HTML: title, banners (fake data suspected, attack, EV
// priority, closures, fast-forward), the loading / finished overlay, camera presets with
// "follow emergency vehicle", the legend and the side-panel toggles.
import { addKo, controllerLabel, lang, pick, scenarioTitle, t } from '../i18n.js';
import { fmtClock, fmtNum, vehicleLabel, APPROACH_NAMES } from '../util.js';
import { $, h, toast } from './dom.js';

addKo({
  Overview: '전체',
  'Whole corridor (0)': '구간 전체 (0)',
  'Junction {j} ({key})': '{j} 교차로 ({key})',
  Top: '위에서',
  'Straight down': '바로 위에서 내려다보기',
  'Follow EV': '긴급차량 따라가기',
  'Chase the newest emergency vehicle (F)': '가장 최근 긴급차량을 따라가요 (F)',
  'Jump to every newly dispatched emergency vehicle': '새로 출동하는 긴급차량마다 카메라를 옮겨요',
  'auto-follow EVs': '긴급차량 자동 추적',
  'The emergency vehicle left the network; camera released.': '긴급차량이 구간을 벗어나서 카메라 추적을 멈췄어요.',
  'Camera following {vehicle}. Drag the view to stop.': '카메라 추적 중: {vehicle}. 화면을 드래그하면 멈춰요.',
  'No emergency vehicle on the road. Dispatch one under Actions.': '도로에 긴급차량이 없어요. 직접 조작에서 출동시켜 보세요.',
  'seed {seed}': '시드 {seed}',
  'nav-app coverage {pct}%': '내비 데이터 비율 {pct}%',
  'Fast-forwarding to {time}…': '{time}까지 빨리 감는 중…',
  'FAKE DATA SUSPECTED at {junction} {approach}: navigation apps report {probe} queued, loop detectors see {detector}':
    '가짜 데이터 의심 · {junction} {approach}: 내비 앱은 대기 {probe}대, 루프 감지기는 {detector}대',
  'Fake-data attack · {n} phantom phones at {junction} {approach}': '가짜 데이터 공격 · {junction} {approach}에 가짜 휴대폰 {n}대',
  'Emergency vehicle priority at {junctions}': '긴급차량 우선 신호 · {junctions}',
  'Road closed: {list}': '도로 폐쇄: {list}',
  'Roads closed: {list}': '도로 폐쇄: {list}',
  'earthquake: bridge damage': '지진: 다리 손상',
  'earthquake: debris': '지진: 잔해',
  'Lost the connection to the twin server. Reconnecting…': '트윈 서버와 연결이 끊겼어요. 다시 연결하는 중…',
  'Connecting…': '연결 중…',
  'No simulation running yet.': '아직 실행 중인 시뮬레이션이 없어요.',
  Start: '시작',
  'Starting SUMO…': 'SUMO 시작 중…',
  'Something went wrong.': '문제가 생겼어요.',
  'Try again': '다시 시도',
  'mean delay': '평균 지연',
  'completed trips': '완료된 통행',
  unfinished: '미완료',
  'p95 travel time': '95백분위 통행 시간',
  'EV travel time': '긴급차량 통행 시간',
  'Run finished': '실행 종료',
  'End of the recording. Replay it, or pick another run above.': '녹화가 끝났어요. 다시 보거나 위에서 다른 실행을 골라 보세요.',
  'Outputs saved to {dir}': '결과 저장 위치: {dir}',
  'Run again': '다시 실행',
  Close: '닫기',
  'Shares nav-app data': '내비 데이터 공유 차량',
  'Brake lights': '브레이크등',
  'Stop bar = signal': '정지선 색 = 신호',
  'Queue length': '대기열 길이',
  'Flooded / closed': '침수 / 폐쇄',
  'Fake phone reports': '가짜 휴대폰 보고',
  'EV priority': '긴급차량 우선',
  Legend: '범례',
});

const ALERT_HOLD_MS = 4000; // alerts flicker per step: hold the banner a bit (like the 3D label)

/** 'N' -> 'north' in English, '북쪽' in Korean (APPROACH_NAMES holds the English words). */
const approachWord = (a) => t(APPROACH_NAMES[a] || a);

/** Camera presets and the follow camera. ctx.camera = this. */
export class CameraControl {
  constructor(ctx) {
    this.ctx = ctx;
    this.view = ctx.view;
    this.vehicles = ctx.layers.vehicles;
    this.pending = null; // vehicle id to follow as soon as it appears
    this.autoFollow = false;
    this.bar = $('#camera-bar');
    this.buttons = new Map();
    const add = (key, label, title, fn) => {
      const b = h('button', { title }, label);
      b.addEventListener('click', fn);
      this.bar.append(b);
      this.buttons.set(key, b);
    };
    add('overview', t('Overview'), t('Whole corridor (0)'), () => this.fly('overview'));
    for (const j of ctx.meta.junctions) add(j, j, t('Junction {j} ({key})', { j, key: j.slice(1) }), () => this.fly(j));
    add('top', t('Top'), t('Straight down'), () => this.fly('top'));
    add('follow', t('Follow EV'), t('Chase the newest emergency vehicle (F)'), () => this.followLatest());
    const auto = h('input', { type: 'checkbox' });
    auto.addEventListener('change', () => (this.autoFollow = auto.checked));
    this.bar.append(h('label', { title: t('Jump to every newly dispatched emergency vehicle') }, auto, t('auto-follow EVs')));
    this.view.onFollowLost = (byUser) => {
      this.setActive(null);
      if (!byUser) toast(t('The emergency vehicle left the network; camera released.'));
    };
    ctx.bus.on('frame', (f) => {
      if (this.autoFollow) for (const e of f.events || []) if (e.type === 'ev_dispatched') this.pending = { id: e.vehicle, until: performance.now() + 15000 };
      if (this.pending) {
        if (this.vehicles.pose(this.pending.id)) {
          this.follow(this.pending.id);
          this.pending = null;
        } else if (performance.now() > this.pending.until) this.pending = null;
      }
    });
    this.setActive('overview');
  }

  setActive(key) {
    for (const [k, b] of this.buttons) b.classList.toggle('active', k === key);
  }

  fly(name) {
    this.pending = null;
    this.view.flyTo(name);
    this.setActive(name);
  }

  follow(id) {
    this.view.setFollow(() => this.vehicles.pose(id));
    this.setActive('follow');
    toast(t('Camera following {vehicle}. Drag the view to stop.', { vehicle: vehicleLabel(id) }));
  }

  followVehicle(id) {
    if (this.vehicles.pose(id)) this.follow(id);
    else this.pending = { id, until: performance.now() + 15000 }; // it appears after the next step
  }

  followLatest() {
    const id = this.vehicles.latestEmergency();
    if (id) this.follow(id);
    else toast(t('No emergency vehicle on the road. Dispatch one under Actions.'));
  }
}

export class ViewportChrome {
  constructor(ctx) {
    this.ctx = ctx;
    this.title = $('#vp-title');
    this.banners = $('#banners');
    this.overlay = $('#vp-overlay');
    this.alertUntil = 0;
    this.lastAlert = null;
    this.status = null;
    this.frame = null;
    this.buildLegend();
    const live = $('#live-view');
    $('#toggle-left').addEventListener('click', () => live.classList.toggle('hide-left'));
    $('#toggle-right').addEventListener('click', () => live.classList.toggle('hide-right'));
    ctx.bus.on('status', (s) => {
      this.status = s;
      this.renderOverlay();
      this.renderTitle();
      this.renderBanners();
    });
    ctx.bus.on('frame', (f) => {
      this.frame = f;
      const alerts = (f.alerts || []).filter((a) => a.type === 'probe_detector_mismatch');
      if (alerts.length) {
        this.alertUntil = performance.now() + ALERT_HOLD_MS;
        this.lastAlert = alerts[0];
        // Paused, no frame or status comes to take the banner down: re-render when it expires.
        clearTimeout(this.alertTimer);
        this.alertTimer = setTimeout(() => this.renderBanners(), ALERT_HOLD_MS + 50);
      }
      this.renderBanners();
    });
    ctx.bus.on('session', () => {
      // A new run: the previous run's alert does not carry over.
      clearTimeout(this.alertTimer);
      this.alertUntil = 0;
      this.lastAlert = null;
    });
    ctx.bus.on('connection', (ok) => {
      this.connected = ok;
      this.renderOverlay();
    });
  }

  hideBootOverlay() {
    this.booted = true;
    this.renderOverlay();
  }

  renderTitle() {
    const s = this.status;
    if (!s || !s.config) {
      this.title.hidden = true;
      return;
    }
    this.title.hidden = false;
    const sc = this.ctx.meta.scenarios.find((x) => x.name === s.config.scenario);
    const ct = this.ctx.meta.controllers.find((x) => x.name === s.config.controller);
    const cov = this.frame && this.frame.coverage != null ? this.frame.coverage : s.config.coverage;
    const sub = [ct ? controllerLabel(ct) : s.config.controller, t('seed {seed}', { seed: s.config.seed })];
    if (cov != null) sub.push(t('nav-app coverage {pct}%', { pct: Math.round(cov * 100) }));
    const note = pick(s, 'note'); // online demo: what this recording shows
    this.title.innerHTML = '';
    this.title.append(h('div', { class: 't1' }, sc ? scenarioTitle(sc) : s.config.scenario), h('div', { class: 't2' }, sub.join(' · ')));
    if (note) this.title.append(h('div', { class: 't3' }, note)); // append(null) would print "null"
  }

  renderBanners() {
    const f = this.frame;
    const s = this.status;
    const list = [];
    if (s && s.fast_forward_to != null) list.push(['info', t('Fast-forwarding to {time}…', { time: fmtClock(s.fast_forward_to) })]);
    if (f) {
      if (performance.now() < this.alertUntil && this.lastAlert) {
        const a = this.lastAlert;
        list.push([
          'alert',
          t('FAKE DATA SUSPECTED at {junction} {approach}: navigation apps report {probe} queued, loop detectors see {detector}', {
            junction: a.junction,
            approach: approachWord(a.approach),
            probe: fmtNum(a.probe_queue, 0),
            detector: a.detector_queue,
          }),
        ]);
      }
      if (f.attack) {
        const text = t('Fake-data attack · {n} phantom phones at {junction} {approach}', { n: f.attack.n, junction: f.attack.junction, approach: approachWord(f.attack.approach) });
        list.push(['attack', text]);
      }
      if ((f.preempting || []).length) list.push(['preempt', t('Emergency vehicle priority at {junctions}', { junctions: f.preempting.join(', ') })]);
      const closed = f.closures || [];
      if (closed.length) {
        const names = closed.map((c) => `${c.edge} (${t(c.cause)})`).join(', ');
        list.push(['info', t(closed.length > 1 ? 'Roads closed: {list}' : 'Road closed: {list}', { list: names })]);
      }
    }
    const key = JSON.stringify(list);
    if (key === this._bannerKey) return;
    this._bannerKey = key;
    this.banners.innerHTML = '';
    for (const [kind, text] of list) this.banners.append(h('div', { class: `banner ${kind}` }, text));
  }

  renderOverlay() {
    const o = this.overlay;
    const s = this.status;
    const show = (html, soft = false, actions = []) => {
      o.hidden = false;
      o.className = `vp-overlay${soft ? ' soft' : ''}`;
      o.innerHTML = '';
      o.append(...html);
      if (actions.length) {
        o.style.pointerEvents = 'auto';
        o.append(h('div', { style: { display: 'flex', gap: '8px' } }, ...actions));
      } else o.style.pointerEvents = soft ? 'none' : 'auto';
    };
    if (!this.booted) return; // the boot message from index.html stays
    if (this.connected === false) return show([h('div', { class: 'spinner' }), h('div', {}, t('Lost the connection to the twin server. Reconnecting…'))], true);
    if (!s) return show([h('div', { class: 'spinner' }), h('div', {}, t('Connecting…'))], true);
    const btn = (label, cls, fn) => h('button', { class: `btn ${cls}`, onclick: fn }, label);
    switch (s.state) {
      case 'idle':
        return show([h('div', {}, t('No simulation running yet.'))], true, [btn(t('Start'), 'primary', () => this.ctx.topbar.start())]);
      case 'loading': {
        // The live server's progress messages are English; the recorded demo's are translated.
        const message = s.message && (lang === 'en' || this.ctx.static) ? s.message : t('Starting SUMO…');
        return show([h('div', { class: 'spinner' }), h('div', {}, message)], true);
      }
      case 'error': {
        // TopBar.retry, like Play / Space: a recording carries on where its download failed.
        return show([h('div', { style: { maxWidth: '560px', color: '#ffd0d0' } }, s.error || t('Something went wrong.'))], false, [btn(t('Try again'), 'primary', () => this.ctx.topbar.retry())]);
      }
      case 'finished': {
        const sum = s.summary || {};
        const items = [
          ['mean delay', sum.mean_delay_s != null ? `${fmtNum(sum.mean_delay_s, 1)} s/veh` : '–'],
          ['completed trips', fmtNum(sum.completed, 0)],
          ['unfinished', sum.unfinished_pct != null ? `${fmtNum(sum.unfinished_pct, 1)}%` : '–'],
          ['p95 travel time', sum.p95_travel_time_s != null ? `${fmtNum(sum.p95_travel_time_s, 0)} s` : '–'],
          ['EV travel time', sum.ev_mean_travel_time_s != null ? `${fmtNum(sum.ev_mean_travel_time_s, 0)} s` : '–'],
        ];
        const where = this.ctx.static ? t('End of the recording. Replay it, or pick another run above.') : t('Outputs saved to {dir}', { dir: s.output_dir || 'results/twin/' });
        return show(
          [
            h('div', { style: { fontWeight: 700, fontSize: '16px' } }, t('Run finished')),
            h('div', { style: { color: '#8b9ab3' } }, where),
            h('div', { class: 'chips', style: { justifyContent: 'center', maxWidth: '520px' } }, ...items.map(([k, v]) => h('span', { class: 'chip' }, `${t(k)}: ${v}`))),
          ],
          false,
          [btn(t('Run again'), 'primary', () => this.ctx.socket.control('reset')), btn(t('Close'), '', () => (o.hidden = true))],
        );
      }
      default:
        o.hidden = true;
    }
  }

  buildLegend() {
    const root = $('#legend');
    const item = (sw, label) => h('div', { class: 'legend-item' }, sw, t(label));
    const sw = (bg, cls = '') => h('span', { class: `sw ${cls}`, style: { background: bg } });
    const body = h('div', { class: 'legend-body' },
      item(sw('#c9ccd1'), 'Car'),
      item(sw('#2f9bff', 'round'), 'Shares nav-app data'),
      item(sw('#d9dcdf'), 'Truck'),
      item(sw('#eef2f4'), 'Bus'),
      item(sw('linear-gradient(90deg,#ff2020 50%,#2a6bff 50%)'), 'Ambulance'),
      item(sw('#c42019'), 'Fire truck'),
      item(sw('#ff2a1f', 'round'), 'Brake lights'),
      item(sw('linear-gradient(90deg,#22e07a,#ffc533,#ff3b3b)'), 'Stop bar = signal'),
      item(sw('linear-gradient(90deg,#22c55e,#fbbf24,#ef4444)'), 'Queue length'),
      item(sw('#3a7cc0'), 'Flooded / closed'),
      item(sw('#b070ff'), 'Fake phone reports'),
      item(h('span', { class: 'sw round', style: { background: 'transparent', boxShadow: 'inset 0 0 0 2px #ff3030' } }), 'EV priority'),
    );
    const head = h('h3', {}, t('Legend'), h('span', {}, '▾'));
    head.addEventListener('click', () => root.classList.toggle('collapsed'));
    root.append(head, body);
    if (window.matchMedia('(max-width: 640px)').matches) root.classList.add('collapsed'); // phones: keep the road visible
  }
}
