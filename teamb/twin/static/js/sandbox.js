// Portable phase-1 scenario builder. Keep the schema aligned with teamb/sandbox.py.
const SCENARIOS = ['rush_hour','off_peak','special_event','emergency','road_closure','sinkhole_cross','earthquake','fake_data_attack'];
const CONTROLLERS = ['fixed_time','coordinated','actuated','max_pressure','max_pressure_probe','ai_recommender','rl'];
const $ = id => document.getElementById(id);
for (const [id, values] of [['scenario',SCENARIOS],['controller',CONTROLLERS]]) {
  for (const name of values) { const opt = document.createElement('option'); opt.value=name; opt.textContent=name.replaceAll('_',' '); $(id).append(opt); }
}
function validate(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw Error('Expected a JSON object');
  const keys=['scenario','controller','seed','demand_scale','ev_preemption','duration_s','schema_version'];
  if (Object.keys(v).some(k=>!keys.includes(k))) throw Error('Configuration contains an unsupported field');
  if (v.schema_version !== 1) throw Error('Unsupported schema version');
  if (!SCENARIOS.includes(v.scenario)) throw Error('Unknown scenario');
  if (!CONTROLLERS.includes(v.controller)) throw Error('Unknown controller');
  if (!Number.isInteger(v.seed) || v.seed<0 || v.seed>2147483647) throw Error('Seed must be an integer between 0 and 2147483647');
  if (typeof v.demand_scale!=='number' || !Number.isFinite(v.demand_scale) || v.demand_scale<.1 || v.demand_scale>3) throw Error('Demand multiplier must be between 0.1 and 3');
  if (typeof v.ev_preemption!=='boolean') throw Error('EMS preemption must be true or false');
  if (v.duration_s!==null && (!Number.isInteger(v.duration_s)||v.duration_s<60||v.duration_s>10800)) throw Error('Duration must be 60–10800 seconds or blank');
  return v;
}
function fromForm() {
  return validate({scenario:$('scenario').value,controller:$('controller').value,
    seed:Number($('seed').value),demand_scale:Number($('demand_scale').value),
    ev_preemption:$('ev_preemption').checked,
    duration_s:$('duration_s').value===''?null:Number($('duration_s').value),schema_version:1});
}
function show() {
  try {
    const v=fromForm(); $('preview').textContent=JSON.stringify(v,null,2);
    const params=JSON.stringify({demand_scale:v.demand_scale});
    $('command').textContent='python -m teamb.experiments run --name sandbox_trial --scenarios '+v.scenario+
      ' --controllers '+v.controller+' --seeds '+v.seed+' --ev-preemption '+(v.ev_preemption?'on':'off')+
      ' --scenario-params '+"'"+params+"'"+(v.duration_s===null?'':' --end '+v.duration_s);
    $('status').textContent='Configuration valid · ready to export';$('status').className='ok';
    return v;
  } catch(e) { $('status').textContent=e.message;$('status').className='error';$('preview').textContent='Invalid configuration';$('command').textContent='';return null; }
}
function fill(v) {
  validate(v);
  for(const id of ['scenario','controller','seed','demand_scale']) $(id).value=v[id];
  $('ev_preemption').checked=v.ev_preemption;$('duration_s').value=v.duration_s??'';
  show();
}
for(const id of ['scenario','controller','seed','demand_scale','ev_preemption','duration_s']) $(id).addEventListener('input',show);
$('reset').addEventListener('click',()=>fill({scenario:'rush_hour',controller:'max_pressure',seed:1,demand_scale:1,ev_preemption:true,duration_s:null,schema_version:1}));
$('export').addEventListener('click',()=>{const v=show();if(!v)return;const blob=new Blob([JSON.stringify(v,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='team-b-scenario.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('copy').addEventListener('click',async()=>{const v=show();if(!v)return;try{await navigator.clipboard.writeText(JSON.stringify(v,null,2));$('status').textContent='Configuration copied';}catch{$('status').textContent='Clipboard unavailable; select the JSON above';}});
$('import').addEventListener('change',async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>100000)throw Error('File too large');fill(JSON.parse(await file.text()));$('status').textContent='Configuration imported and validated';}catch(err){$('status').textContent='Import rejected: '+err.message;$('status').className='error';}e.target.value='';});
show();

const liveUrl = $('live_url');
const isStaticPages = location.hostname.endsWith('.github.io');
const initialLive = localStorage.getItem('teamb_live_url') || (isStaticPages ? '' : location.origin);
liveUrl.value = initialLive;
$('launch_live').addEventListener('click', () => {
  const cfg = show();
  if (!cfg) return;
  try {
    const target = new URL(liveUrl.value.trim());
    if (target.protocol !== 'https:' && !(target.protocol === 'http:' && ['localhost','127.0.0.1'].includes(target.hostname))) {
      throw Error('Use an HTTPS cloud URL or a local http://localhost URL.');
    }
    if (target.username || target.password || target.search || target.hash) throw Error('Enter a server origin only, without credentials or query parameters.');
    if (isStaticPages && target.hostname === location.hostname) throw Error('GitHub Pages cannot run SUMO; enter the separate cloud simulator URL.');
    localStorage.setItem('teamb_live_url', target.origin);
    const url = new URL('/', target.origin);
    for (const [key,value] of Object.entries({
      scenario:cfg.scenario, controller:cfg.controller, seed:cfg.seed,
      demand:cfg.demand_scale, end:cfg.duration_s, ev:cfg.ev_preemption?1:0,
      speed:2
    })) if (value !== null) url.searchParams.set(key, String(value));
    window.location.assign(url.href);
  } catch(err) {
    $('status').textContent='Live launch: '+err.message;
    $('status').className='error';
  }
});
