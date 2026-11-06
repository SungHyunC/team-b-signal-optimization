// Scenario Sandbox page (static/sandbox.html): build, validate, export and import a run
// configuration, show the equivalent CLI commands and launch it on a live twin. The schema,
// validation and commands are in sandbox_schema.js (shared with tests/js and kept aligned with
// teamb/sandbox.py). Served by the twin, the lists and limits come from /api/sandbox/schema;
// on static GitHub Pages the built-in ones are used.
import { addKo, mountLanguageSwitch, t, translatePage } from './i18n.js';
import {
  ConfigError,
  DEFAULTS,
  EXPORT_FILE,
  experimentCommand,
  FALLBACK_SCHEMA,
  launchUrl,
  loadSchema,
  MAX_IMPORT_BYTES,
  parseImport,
  sandboxRunCommand,
  validate as validateConfig,
  WARMUP_S,
} from './sandbox_schema.js';

addKo({
  // sandbox.html (data-i18n)
  'Scenario Sandbox · Team B': '시나리오 샌드박스 · B팀',
  '← Back to Signal Twin': '← Signal Twin으로 돌아가기',
  'Scenario Sandbox': '시나리오 샌드박스',
  'Build, validate, export and import reproducible SUMO experiment configurations. This page does not run simulations itself: run the exported file with the commands below, or launch it on a live SUMO server.':
    '재현 가능한 SUMO 실험 설정을 만들고, 검증하고, 내보내고, 불러와요. 이 페이지가 직접 시뮬레이션을 돌리지는 않아요. 내보낸 파일을 아래 명령으로 실행하거나 실시간 SUMO 서버에서 실행해 보세요.',
  'Configure your experiment': '실험 설정',
  'Preset scenario': '기본 시나리오',
  'Signal controller': '신호 제어 방식',
  'Traffic demand multiplier': '교통 수요 배율',
  '(1.0 = preset demand)': '(1.0 = 시나리오 기본 수요)',
  'Random seed': '난수 시드',
  'Duration in seconds': '실행 시간 (초)',
  'Enable emergency vehicle signal preemption': '긴급차량 우선 신호 켜기',
  'Reset preset': '기본값으로',
  'Download JSON': 'JSON 내려받기',
  'Import saved configuration': '저장한 설정 불러오기',
  'Emergency dispatches and road closures are defined by the selected preset. The EMS switch controls signal preemption; it does not create emergency vehicles.':
    '긴급차량 출동과 도로 폐쇄는 고른 시나리오에 정해져 있어요. 긴급차량 스위치는 우선 신호만 켜고 끄며, 긴급차량을 만들지는 않아요.',
  'Validated configuration': '검증된 설정',
  'Copy JSON': 'JSON 복사',
  'How to reproduce the experiment': '실험을 재현하는 방법',
  "Both commands run the same experiment in SUMO and write a report under results/experiments/sandbox_trial/. They use the scenario's own navigation-app coverage. Keep the JSON together with the project commit SHA and the SUMO version.":
    '두 명령 모두 SUMO에서 같은 실험을 돌리고 results/experiments/sandbox_trial/ 아래에 보고서를 써요. 내비 데이터 비율은 시나리오 기본값을 써요. JSON 파일은 프로젝트 커밋 SHA, SUMO 버전과 함께 보관하세요.',
  'After Download JSON (saves sandbox_trial.json):': 'JSON 내려받기 후 (sandbox_trial.json으로 저장돼요):',
  'Or the same run without the file:': '또는 파일 없이 같은 실행:',
  'Run a live SUMO simulation': '실시간 SUMO 시뮬레이션 실행',
  'This launches a real SUMO run on a separate cloud server, not in GitHub Pages. The server must be deployed, online and accessible to you.':
    'GitHub Pages가 아닌 별도 클라우드 서버에서 실제 SUMO를 실행해요. 서버가 배포되어 켜져 있고 접속할 수 있어야 해요.',
  'Cloud simulator address': '클라우드 시뮬레이터 주소',
  '(for example https://your-live-sumo.onrender.com)': '(예: https://your-live-sumo.onrender.com)',
  'Launch LIVE SUMO →': '실시간 SUMO 실행 →',
  'Live runs require a hosted SUMO server. All visitors connected to one instance share the same simulation.':
    '실시간 실행에는 SUMO 서버가 필요해요. 한 서버에 접속한 모든 방문자가 같은 시뮬레이션을 함께 봐요.',
  'What each setting means': '설정별 의미',
  'Scenario:': '시나리오:',
  'the network demand and timed events.': '도로망의 교통 수요와 정해진 시각의 사건이에요.',
  'Controller:': '신호 제어 방식:',
  'the traffic-light decision rule.': '신호등을 바꾸는 규칙이에요.',
  'Seed:': '시드:',
  'reproducible random traffic.': '같은 값이면 같은 무작위 교통이 재현돼요.',
  'Demand multiplier:': '수요 배율:',
  'scale the existing vehicle flows.': '기존 차량 흐름을 늘리거나 줄여요.',
  'Preemption:': '우선 신호:',
  'emergency-vehicle signal priority.': '긴급차량에 녹색 신호를 먼저 줘요.',
  'Duration:': '실행 시간:',
  'optional end time in simulated seconds; the first 900 s are warm-up and are not measured.':
    '선택 사항인 종료 시각(시뮬레이션 초)이에요. 처음 900초는 워밍업이라 측정하지 않아요.',
  'Open recorded digital twin →': '녹화된 디지털 트윈 열기 →',
  // this file
  'Use preset duration': '시나리오 기본 시간',
  '(blank = preset duration; {min}–{max} s, the first {warmup} s are warm-up)': '(비우면 시나리오 기본 시간 · {min}–{max}초, 처음 {warmup}초는 워밍업)',
  'Scenarios, controllers and limits from this server.': '이 서버가 알려 준 시나리오, 신호 제어 방식, 제한값이에요.',
  'Built-in scenarios, controllers and limits (static page).': '내장된 시나리오, 신호 제어 방식, 제한값이에요 (정적 페이지).',
  'Configuration valid · ready to export': '설정이 유효해요 · 내보낼 수 있어요',
  'Invalid configuration': '잘못된 설정',
  'Configuration imported and validated': '설정을 불러와서 검증했어요',
  'Import rejected: {error}': '불러오지 못했어요: {error}',
  'Configuration copied': '설정을 복사했어요',
  'Clipboard unavailable; select the JSON above': '클립보드를 쓸 수 없어요. 위의 JSON을 직접 선택해 주세요',
  'Live launch: {error}': '실시간 실행: {error}',
  'Enter the cloud simulator address.': '클라우드 시뮬레이터 주소를 입력하세요.',
  'That is not a valid address.': '올바른 주소가 아니에요.',
  'Use an HTTPS cloud URL or a local http://localhost URL.': 'HTTPS 클라우드 주소나 로컬 http://localhost 주소를 입력하세요.',
  'Enter a server origin only, without credentials or query parameters.': '계정 정보나 쿼리 없이 서버 주소만 입력하세요.',
  'GitHub Pages cannot run SUMO; enter the separate cloud simulator URL.': 'GitHub Pages에서는 SUMO를 실행할 수 없어요. 별도 클라우드 시뮬레이터 주소를 입력하세요.',
  // validation (sandbox_schema.js)
  'Expected a JSON object': 'JSON 객체여야 해요',
  'Not valid JSON: {error}': '올바른 JSON이 아니에요: {error}',
  'Unsupported field: {field}': '지원하지 않는 항목이에요: {field}',
  'Unsupported schema version': '지원하지 않는 schema_version이에요',
  'Unknown scenario: {name}': '알 수 없는 시나리오예요: {name}',
  'Unknown controller: {name}': '알 수 없는 신호 제어 방식이에요: {name}',
  'Seed must be an integer between {min} and {max}': '시드는 {min}–{max} 사이의 정수여야 해요',
  'Demand multiplier must be between {min} and {max}': '수요 배율은 {min}–{max} 사이여야 해요',
  'EMS preemption must be true or false': '긴급차량 우선 신호는 true 또는 false여야 해요',
  'Duration must be blank or a whole number of seconds between {min} and {max}': '실행 시간은 비우거나 {min}–{max}초 사이의 정수여야 해요',
  '{field} must be a whole number (write 5, not 5.0)': '{field}은(는) 정수여야 해요 (5.0이 아니라 5로 써 주세요)',
  'File too large': '파일이 너무 커요',
  'Seed is required': '시드를 입력하세요',
  'Demand multiplier is required': '수요 배율을 입력하세요',
});

const $ = (id) => document.getElementById(id);
// Storage is optional: blocked cookies (SecurityError) or a full quota must not break the page.
const store = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      // the address field still works for this visit
    }
  },
};
const isStaticPages = location.hostname.endsWith('.github.io');
const servedOverHttp = location.protocol === 'http:' || location.protocol === 'https:';
let schema = FALLBACK_SCHEMA;

translatePage();
mountLanguageSwitch($('lang-switch'));
$('duration_s').placeholder = t('Use preset duration');

/** Validate against the current schema (teamb/sandbox.py parse_sandbox_config rules). */
function validate(v) {
  return validateConfig(v, schema);
}

const message = (err) => (err instanceof ConfigError ? t(err.key, err.vars) : err.message);

function setStatus(text, cls) {
  $('status').textContent = text;
  $('status').className = cls;
}

/** Scenario/controller options and input limits from the schema; keeps the current choice. */
function applySchema(source) {
  for (const [id, values] of [['scenario', schema.scenarios], ['controller', schema.controllers]]) {
    const select = $(id);
    const keep = select.value || DEFAULTS[id];
    select.innerHTML = '';
    for (const name of values) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name.replaceAll('_', ' ');
      select.append(opt);
    }
    select.value = values.includes(keep) ? keep : values.includes(DEFAULTS[id]) ? DEFAULTS[id] : values[0];
  }
  const { seed, demand_scale: demand, duration_s: duration } = schema.limits;
  [$('seed').min, $('seed').max] = seed;
  [$('demand_scale').min, $('demand_scale').max] = demand;
  [$('duration_s').min, $('duration_s').max] = duration;
  $('duration_hint').textContent = t('(blank = preset duration; {min}–{max} s, the first {warmup} s are warm-up)', { min: duration[0], max: duration[1], warmup: WARMUP_S });
  $('schema_source').textContent = source === 'server' ? t('Scenarios, controllers and limits from this server.') : t('Built-in scenarios, controllers and limits (static page).');
}

function fromForm() {
  if ($('seed').value.trim() === '') throw new ConfigError('Seed is required'); // Number('') would be 0
  if ($('demand_scale').value.trim() === '') throw new ConfigError('Demand multiplier is required');
  const duration = $('duration_s').value.trim();
  return validate({
    scenario: $('scenario').value,
    controller: $('controller').value,
    seed: Number($('seed').value),
    demand_scale: Number($('demand_scale').value),
    ev_preemption: $('ev_preemption').checked,
    duration_s: duration === '' ? null : Number(duration),
    schema_version:1,
  });
}

function show() {
  try {
    const v = fromForm();
    $('preview').textContent = JSON.stringify(v, null, 2);
    $('command_file').textContent = sandboxRunCommand(EXPORT_FILE);
    $('command').textContent = experimentCommand(v);
    setStatus(t('Configuration valid · ready to export'), 'ok');
    return v;
  } catch (err) {
    setStatus(message(err), 'error');
    $('preview').textContent = t('Invalid configuration');
    $('command_file').textContent = '';
    $('command').textContent = '';
    return null;
  }
}

/** Put a configuration (missing fields = defaults) into the form. */
function fill(v) {
  const c = validate(v);
  for (const id of ['scenario', 'controller', 'seed', 'demand_scale']) $(id).value = c[id];
  $('ev_preemption').checked = c.ev_preemption;
  $('duration_s').value = c.duration_s ?? '';
  show();
}

for (const id of ['scenario', 'controller', 'seed', 'demand_scale', 'ev_preemption', 'duration_s']) $(id).addEventListener('input', show);
$('reset').addEventListener('click', () => fill(DEFAULTS));
$('export').addEventListener('click', () => {
  const v = show();
  if (!v) return;
  const blob = new Blob([`${JSON.stringify(v, null, 2)}\n`], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = EXPORT_FILE; // the name the `teamb sandbox run` command above uses
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('copy').addEventListener('click', async () => {
  const v = show();
  if (!v) return;
  try {
    await navigator.clipboard.writeText(JSON.stringify(v, null, 2));
    setStatus(t('Configuration copied'), 'ok');
  } catch {
    setStatus(t('Clipboard unavailable; select the JSON above'), 'error');
  }
});
$('import').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    if (file.size > MAX_IMPORT_BYTES) throw new ConfigError('File too large');
    fill(parseImport(await file.text(), schema)); // same rules as `teamb sandbox validate`
    setStatus(t('Configuration imported and validated'), 'ok');
  } catch (err) {
    setStatus(t('Import rejected: {error}', { error: message(err) }), 'error');
  }
  e.target.value = '';
});

applySchema('built-in');
show();
// Served by the twin: its own lists and limits (e.g. a newly registered controller).
loadSchema({ skip: isStaticPages || !servedOverHttp }).then(({ schema: s, source }) => {
  if (source !== 'server') return;
  schema = s;
  applySchema(source);
  show();
});

// --- launch on a live twin -------------------------------------------------------------------
const liveUrl = $('live_url');
liveUrl.value = store.get('teamb_live_url') || (isStaticPages || !servedOverHttp ? '' : location.origin);
$('launch_live').addEventListener('click', () => {
  const cfg = show();
  if (!cfg) return;
  try {
    const text = liveUrl.value.trim();
    if (!text) throw new ConfigError('Enter the cloud simulator address.');
    let target;
    try {
      target = new URL(text);
    } catch {
      throw new ConfigError('That is not a valid address.');
    }
    if (target.protocol !== 'https:' && !(target.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(target.hostname))) {
      throw new ConfigError('Use an HTTPS cloud URL or a local http://localhost URL.');
    }
    if (target.username || target.password || target.search || target.hash) throw new ConfigError('Enter a server origin only, without credentials or query parameters.');
    if (isStaticPages && target.hostname === location.hostname) throw new ConfigError('GitHub Pages cannot run SUMO; enter the separate cloud simulator URL.');
    store.set('teamb_live_url', target.origin);
    window.location.assign(launchUrl(target.origin, cfg)); // starts at 0:00 with the scenario's coverage
  } catch (err) {
    setStatus(t('Live launch: {error}', { error: message(err) }), 'error');
  }
});
