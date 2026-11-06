// Language switch: English / 한국어. The code keeps the English text and t() looks up the
// Korean; a string without a translation stays English, so adding text never breaks anything.
//
//   import { addKo, t } from '../i18n.js';
//   addKo({ 'Start': '시작', 'Starting {scenario}…': '{scenario} 시작 중…' });
//   button.textContent = t('Start');
//   toast(t('Starting {scenario}…', { scenario: name }));
//
// Each module registers its Korean next to its English (addKo runs when the module loads,
// before any panel is built). The language comes from ?lang=, then the last choice, then the
// browser. Switching reloads the page and keeps the run, time and speed (switchLanguage), so
// panels never have to re-render themselves. Static labels in index.html carry data-i18n
// (text) or data-i18n-title (tooltip) and are translated by translatePage().

const KO = Object.create(null); // no inherited keys: t("constructor") stays "constructor"
const STORE_KEY = 'twin.lang';
export const LANGS = { en: 'EN', ko: '한국어' };
export const lang = detect();

/** True only for a language code we ship (not for inherited keys such as 'constructor'). */
export function isLang(code) {
  return typeof code === 'string' && Object.prototype.hasOwnProperty.call(LANGS, code);
}

function detect() {
  // globalThis.*: the pure modules that import this one also run under `node --test tests/js/`.
  const asked = new URLSearchParams(globalThis.location?.search || '').get('lang');
  if (isLang(asked)) return asked;
  try {
    const saved = localStorage.getItem(STORE_KEY);
    if (isLang(saved)) return saved;
  } catch {
    // storage blocked (private mode), or no storage at all: fall through to the browser language
  }
  return (globalThis.navigator?.language || '').toLowerCase().startsWith('ko') ? 'ko' : 'en';
}

/** Register Korean translations: { 'English text': '한국어', 'With {var}': '{var} 포함' }. */
export function addKo(dict) {
  Object.assign(KO, dict);
}

/** The text in the current language, with {name} placeholders filled from vars. */
export function t(text, vars) {
  let s = lang === 'ko' && KO[text] != null ? KO[text] : text;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? String(vars[k]) : m));
  return s;
}

/** obj.<field>_ko in Korean when the server or a recording provides one, else obj.<field>. */
export function pick(obj, field) {
  if (!obj) return null;
  return (lang === 'ko' && obj[`${field}_ko`]) || obj[field];
}

// --- names shared by several panels --------------------------------------------------------
const CONTROLLERS_KO = {
  fixed_time: ['고정 신호 (90초)', '매 90초 주기로 같은 신호, 50:50 배분, 연동 없음. 우리의 출발점이에요.'],
  coordinated: ['연동 신호 (그린웨이브)', '고정 신호에 오프셋을 줘서 동쪽 방향 차량 무리가 교차로마다 녹색 신호를 만나게 해요.'],
  actuated: [
    '감응 신호 (차량 감지)',
    '루프 감지기에 차가 계속 들어오면 녹색을 연장하고, 3초 넘게 끊기거나 최대 녹색(50초)에 이르면 바꿔요. 반대편에 차가 있을 때만 바꿔요.',
  ],
  max_pressure: ['맥스프레셔', '5초마다 압력(상류 차량 수 − 하류 차량 수, 루프 감지기 기준)이 큰 방향에 녹색을 줘요. 신호 계획이 필요 없어요.'],
  max_pressure_probe: [
    '맥스프레셔 (내비 데이터만, 방어 없음)',
    '내비 앱 데이터만 그대로 믿는 맥스프레셔예요. 가짜 데이터 공격을 걸면 속는 모습을 볼 수 있고, 감지기 교차검증을 켜는 것이 해결책이에요.',
  ],
  ai_recommender: [
    'AI 추천 (엔지니어 승인)',
    '내비 앱 데이터만으로 교통량을 추정하고 시뮬레이션(Optuna)으로 더 나은 신호 계획을 찾아요. 엔지니어가 승인하면 적용해요. 구글 Project Green Light와 같은 방식이에요.',
  ],
  rl: [
    '강화학습 (Q-테이블)',
    '출퇴근 교통으로 학습한 표 기반 Q-러닝이에요. 5초마다 교차로마다 감지기 대기열을 보고 녹색을 유지할지 바꿀지 정하고, 안전은 감독기가 맡아요.',
  ],
};

const SCENARIO_DESCRIPTIONS_KO = {
  rush_hour:
    '도심으로 향하는 아침 출근 시간이에요. 동쪽 방향 간선도로 교통이 늘어나 25분간 최고조에 이른 뒤 줄어들고, 서쪽 방향은 적고, 교차 도로는 크기가 제각각이에요. 고정 신호에서는 실제 대기열이 생기고 적응형 제어가 이길 여지가 커요.',
  off_peak: '트럭이 많은 한산하고 고른 야간 교통이에요. 고정 90초 주기는 빈 교차로에서도 기다리게 만들고, 감지기 감응 제어가 지연과 정지를 가장 많이 줄여요.',
  special_event:
    '저녁 교통 중에 J3 북쪽 경기장 주차장이 비워지면서 약 30분 동안 시간당 680대가 1차로 교차 도로로 J3에 몰려요. 좋은 제어라면 간선도로를 막지 않으면서 J3의 남북 녹색을 늘려요.',
  emergency:
    '출퇴근 시간에 구급차와 소방차 10대가 간선도로 양방향, 각 교차 도로, 회전 경로로 구간을 지나가요. 신호가 녹색 길을 열어 주고, 긴급차량 통행 시간과 다른 차들의 추가 지연을 측정해요.',
  road_closure:
    '갑작스러운 침수로 출근 시간 30분 동안 J2–J3 사이 동쪽 방향 간선도로가 막혀요. 차들은 뒷길(J2 → N2 → N3 → J3, 또는 N1)로 우회하고, 내비 앱 사용자는 실시간 통행 시간으로 경로를 바꿔요. 정체가 얼마나 멀리, 오래 퍼지고 얼마나 빨리 회복되는지 측정해요.',
  sinkhole_cross:
    '싱크홀로 J2 북쪽 교차 도로(J2 ↔ N2, 양방향)가 30분간 막혀요. 남북 교통이 J1이나 J3와 뒷길로 우회하면서 이웃 교차로에 회전 교통이 늘어나요. 교차로 사이 정체 전이를 시험해요.',
  earthquake:
    't = 1200초에 지진으로 J3–J4 다리가 손상되고(3000초까지 양방향 폐쇄) J1 북쪽 교차 도로에 잔해가 떨어져요(3600초까지 폐쇄). 구급차와 소방차 7대가 사방에서 출동해 열린 길을 찾아야 해요.',
  fake_data_attack:
    '2020년 베를린 사례(손수레에 휴대폰 99대를 싣고 구글 지도에 가짜 정체를 만든 일)처럼, 출근 시간에 가짜 내비 데이터가 J2 북쪽 진입로에 긴 대기열이 있다고 보고해요. 내비 데이터 기반 제어가 속는지, 루프 감지기 교차검증이 잡아내는지 봐요.',
};

/** A controller from meta.controllers (or {name}) -> its label in the current language. */
export function controllerLabel(c) {
  if (!c) return '';
  if (lang === 'ko') return c.label_ko || (CONTROLLERS_KO[c.name] || [])[0] || c.label || c.name;
  return c.label || c.name;
}

export function controllerDescription(c) {
  if (!c) return '';
  if (lang === 'ko') return c.description_ko || (CONTROLLERS_KO[c.name] || [])[1] || c.description || '';
  return c.description || '';
}

/** A scenario from meta.scenarios -> its title (the scenarios carry title_ko). */
export function scenarioTitle(s) {
  return s ? pick(s, 'title') || s.name : '';
}

export function scenarioDescription(s) {
  if (!s) return '';
  return (lang === 'ko' && (s.description_ko || SCENARIO_DESCRIPTIONS_KO[s.name])) || s.description || '';
}

// Words several panels use: t('north'), t('Ambulance'), t('arterial'), ...
addKo({
  north: '북쪽',
  south: '남쪽',
  east: '동쪽',
  west: '서쪽',
  eastbound: '동쪽 방향',
  westbound: '서쪽 방향',
  northbound: '북쪽 방향',
  southbound: '남쪽 방향',
  arterial: '간선도로',
  cross: '교차 도로',
  back: '뒷길',
  Ambulance: '구급차',
  'Fire truck': '소방차',
  Car: '승용차',
  Truck: '트럭',
  Bus: '버스',
  Flood: '침수',
  Sinkhole: '싱크홀',
  'Crash / incident': '사고',
  flood: '침수',
  sinkhole: '싱크홀',
  accident: '사고',
});

// --- the page and the switch ----------------------------------------------------------------
/** Translate the static labels in index.html (data-i18n / data-i18n-title) and the tab title. */
export function translatePage(root = document) {
  document.documentElement.lang = lang;
  document.title = t(document.title);
  for (const el of root.querySelectorAll('[data-i18n]')) el.textContent = t(el.textContent.trim());
  for (const el of root.querySelectorAll('[data-i18n-title]')) el.title = t(el.title);
}

/** EN | 한국어 buttons. stateParams() returns URL parameters that bring the viewer back to
 *  the same moment after the reload (scenario, controller, start, speed, ...); a null value
 *  removes that parameter from the URL. */
export function mountLanguageSwitch(root, stateParams = () => ({})) {
  for (const [code, label] of Object.entries(LANGS)) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    b.title = code === 'ko' ? '한국어로 보기' : 'Show in English';
    if (code === lang) b.className = 'active';
    b.addEventListener('click', () => switchLanguage(code, stateParams()));
    root.append(b);
  }
}

export function switchLanguage(next, params = {}) {
  if (next === lang || !isLang(next)) return;
  try {
    localStorage.setItem(STORE_KEY, next);
  } catch {
    // the URL parameter below still carries the choice
  }
  const url = new URL(location.href);
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === '') url.searchParams.delete(k); // e.g. a demand= left over from an earlier link
    else url.searchParams.set(k, v);
  }
  url.searchParams.set('lang', next);
  location.replace(url.toString());
}
