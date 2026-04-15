"""Rehearsal-only dashboard — extends the day-of `hack.ui.app` with mic and cue controls.

This FastAPI app is completely separate from the day-of dashboard. Running
`hack ui` gives you the clean demo dashboard; running `hack ui --rehearsal`
gives you this one, with mic-to-cue and scenario telemetry overlays.

Never used on event day. The `/cue` endpoint writes to `runs/live_cues.ndjson`
which only `hack.rehearsal.runner` consumes.
"""

from __future__ import annotations

import json as _json
import time as _time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

# Reuse the core routes (camera + events) from the day-of app.
from hack.ui.app import app as core_app

app = FastAPI(title="hack rehearsal dashboard")

# Mount the core app so /camera.jpg and /events are available unchanged.
app.mount("/base", core_app)
# Also expose them at root paths to keep the dashboard URL scheme identical.
for route in core_app.router.routes:
    if getattr(route, "path", None) in ("/camera.jpg", "/events"):
        app.router.routes.append(route)


LIVE_CUES_PATH = Path("runs/live_cues.ndjson")


REHEARSAL_HTML = r"""
<!doctype html>
<html><head><title>HACK//REHEARSAL</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=VT323&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a140a;
  --bg-deep:#060c06;
  --fg:#4cff4c;
  --fg-dim:#22a022;
  --fg-mid:#2fd62f;
  --amber:#ffb347;
  --amber-dim:#aa6f1f;
  --red:#ff4545;
  --red-bg:#2a0808;
  --panel:#0c1a0c;
  --border:#1f401f;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg-deep);color:var(--fg);font-family:"Share Tech Mono","VT323",Menlo,monospace;font-size:14px}
body{background:
  radial-gradient(ellipse at center, #0b1a0b 0%, #050a05 100%);
  position:relative;overflow:hidden}
/* CRT scanlines + subtle flicker */
body::before{content:"";position:fixed;inset:0;pointer-events:none;background:
  repeating-linear-gradient(to bottom, rgba(0,0,0,0) 0, rgba(0,0,0,0) 2px, rgba(0,0,0,0.18) 3px);
  z-index:1000;mix-blend-mode:multiply}
body::after{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.55) 120%);z-index:999}
@keyframes flicker{0%,100%{opacity:1}50%{opacity:.94}}
.grid{display:grid;grid-template-columns:minmax(320px,34%) 1fr;gap:10px;padding:10px;height:100vh;position:relative;z-index:1}
.panel{background:var(--panel);border:1px solid var(--border);box-shadow:inset 0 0 12px rgba(76,255,76,.05);padding:8px 10px;display:flex;flex-direction:column;min-height:0}
.panel .chrome{display:flex;align-items:center;gap:10px;border-bottom:1px dashed var(--border);margin-bottom:6px;padding-bottom:4px;text-transform:uppercase;letter-spacing:.15em;font-size:11px;color:var(--fg-dim)}
.panel .chrome .label{color:var(--amber)}
.panel .chrome .tag{font-size:10px;background:var(--bg);border:1px solid var(--border);padding:1px 6px;color:var(--fg-mid);letter-spacing:.1em}
.left-col{display:flex;flex-direction:column;gap:10px;min-height:0}
.right-col{display:grid;grid-template-rows:auto auto auto 1fr;gap:10px;min-height:0}
button,input{background:var(--bg);border:1px solid var(--border);color:var(--fg);padding:5px 9px;font-family:inherit;font-size:13px;letter-spacing:.08em;text-transform:uppercase}
button{cursor:pointer;transition:background .1s}
button:hover{background:var(--bg-deep);border-color:var(--fg-mid)}
button.rec{background:var(--red-bg);border-color:var(--red);color:var(--red);animation:flicker 1s infinite}
input{text-transform:none}
input::placeholder{color:var(--fg-dim)}
.cue-line{background:var(--bg);border:1px solid var(--border);padding:4px 8px;font-size:12px;color:var(--amber);min-height:1em}
.cue-line.dim{color:var(--fg-dim)}
.state{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--fg-dim)}
.state .dot{width:8px;height:8px;background:var(--fg-dim);box-shadow:0 0 6px var(--fg-dim)}
.state .dot.vlm{background:var(--fg-mid);box-shadow:0 0 8px var(--fg-mid);animation:flicker .6s infinite}
.state .dot.planner{background:var(--amber);box-shadow:0 0 8px var(--amber);animation:flicker .6s infinite}
.state .dot.acting{background:var(--fg);box-shadow:0 0 10px var(--fg)}
.state .dot.error{background:var(--red);box-shadow:0 0 10px var(--red)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;font-size:12px;color:var(--fg-dim)}
.kv .k{color:var(--amber-dim);text-transform:uppercase;letter-spacing:.1em;font-size:10px;align-self:center}
.kv .v{color:var(--fg);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
img{width:100%;height:auto;image-rendering:pixelated;background:#000;border:1px solid var(--border);flex:1;object-fit:contain;filter:contrast(1.05) brightness(1.02)}
.list{overflow-y:auto;font-size:12px;display:flex;flex-direction:column;gap:2px;padding-right:2px}
.list::-webkit-scrollbar{width:6px}
.list::-webkit-scrollbar-thumb{background:var(--border)}
.row{padding:2px 6px;border-left:2px solid var(--border);background:rgba(34,160,34,.04);line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .t{color:var(--fg-dim);margin-right:6px;font-size:11px}
.row.voice{border-left-color:var(--amber);color:var(--amber)}
.row.voice .who{color:var(--fg-mid);margin-right:4px}
.row.move{border-left-color:var(--fg-mid);color:var(--fg)}
.row.turn{border-left-color:#8fe68f;color:var(--fg)}
.row.emote{border-left-color:#c0ffc0;color:#c0ffc0}
.row.speak{border-left-color:var(--amber);color:#ffd580}
.row.grip{border-left-color:#ffd580;color:#ffd580}
.row.prebaked::after{content:" [pre-baked]";color:var(--fg-dim);font-size:10px}
.row.alert{background:var(--red-bg);color:var(--red);border-left-color:var(--red)}
.row.alert.flash{animation:alert-flash 1.2s ease-out 3}
.row.ok{background:rgba(76,255,76,.1);color:var(--fg);border-left-color:var(--fg)}
@keyframes alert-flash{0%,100%{background:var(--red-bg)}50%{background:#601818}}
.plan-card{display:flex;flex-direction:column;gap:4px}
.plan-card .title{font-size:11px;color:var(--amber-dim);letter-spacing:.1em;text-transform:uppercase}
.plan-card .cue{color:var(--amber);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plan-steps{display:flex;flex-direction:column;gap:2px;max-height:28vh;overflow-y:auto}
.plan-step{padding:3px 8px;border-left:2px solid var(--border);background:rgba(34,160,34,.03);font-size:12px;display:flex;align-items:center;gap:8px}
.plan-step .idx{color:var(--fg-dim);width:28px;font-size:11px}
.plan-step .txt{flex:1;overflow:hidden;text-overflow:ellipsis}
.plan-step .val{font-size:10px;color:var(--fg-dim);text-transform:uppercase;letter-spacing:.1em}
.plan-step.active{border-left-color:var(--amber);background:rgba(255,179,71,.08);color:var(--amber);box-shadow:0 0 8px rgba(255,179,71,.2) inset}
.plan-step.done{border-left-color:var(--fg-mid);color:var(--fg-dim);opacity:.7}
.plan-step.done .val{color:var(--fg-mid)}
.plan-step.done .txt::before{content:"✓ "}
.plan-step .val.pre{color:var(--fg-mid)}
.plan-step .val.llm{color:var(--amber-dim)}
h1.logo{margin:0;font:22px/1 "VT323",monospace;letter-spacing:.1em;color:var(--fg)}
h1.logo::before{content:"▓ "}
h1.logo .sub{color:var(--amber);font-size:12px;margin-left:10px;letter-spacing:.2em}
.mini{font-size:11px;color:var(--fg-dim)}
</style></head>
<body>
<div class="grid">
  <div class="left-col">
    <div class="panel" style="flex:0 0 auto">
      <div class="chrome">
        <h1 class="logo">HACK//REHEARSAL<span class="sub">v0.1 — DIS2026X1</span></h1>
        <span class="tag" id="env-tag">—</span>
      </div>
      <div class="cue-line" id="cue-panel">&gt; awaiting voice command_</div>
    </div>
    <div class="panel" style="flex:1 1 auto">
      <div class="chrome"><span class="label">LIVE CAMERA</span><span id="env-hint" class="mini"></span></div>
      <img id="cam" src="/camera.jpg"/>
    </div>
  </div>

  <div class="right-col">
    <!-- Controls + model status (compact) -->
    <div class="panel">
      <div class="chrome"><span class="label">Console</span>
        <span class="state"><span class="dot" id="state-dot"></span><span id="state-text">idle</span></span>
        <span class="mini" id="mean-ms" style="margin-left:auto"></span>
      </div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <button id="mic">&gt; mic off</button>
        <input id="txt" placeholder="type a cue + enter" style="flex:1">
      </div>
      <div class="kv">
        <span class="k">LLM</span><span class="v" id="llm-model">—</span>
        <span class="k">@ host</span><span class="v" id="llm-host">—</span>
        <span class="k">VLM</span><span class="v" id="vlm-model">—</span>
        <span class="k">@ host</span><span class="v" id="vlm-host">—</span>
        <span class="k">VLM ms</span><span class="v" id="vlm-ms">—</span>
        <span class="k">Planner ms</span><span class="v" id="planner-ms">—</span>
      </div>
      <div class="mini" id="mic-status" style="margin-top:4px"></div>
    </div>

    <!-- Plan decomposition -->
    <div class="panel">
      <div class="chrome"><span class="label">Plan decomposition</span>
        <span class="tag" id="plan-progress-tag">—</span>
        <span class="mini" id="plan-validation" style="margin-left:auto"></span>
      </div>
      <div class="plan-card">
        <div class="title">active cue</div>
        <div class="cue" id="plan-cue">— no active plan —</div>
        <div class="title" style="margin-top:4px">steps</div>
        <div class="plan-steps" id="plan-steps"></div>
      </div>
    </div>

    <!-- Voice commands -->
    <div class="panel">
      <div class="chrome"><span class="label">Voice commands</span><span class="tag" id="voice-n">0</span></div>
      <div id="voice" class="list" style="max-height:18vh"></div>
    </div>

    <!-- Alerts (errors only) + movement log -->
    <div class="panel" style="flex:1 1 auto">
      <div class="chrome"><span class="label">Alerts</span><span class="tag" id="alerts-n">0</span>
        <span class="label" style="margin-left:14px">Movement log</span><span class="tag" id="moves-n">0</span></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;min-height:0;flex:1">
        <div id="alerts" class="list" style="min-height:0"></div>
        <div id="moves" class="list" style="min-height:0"></div>
      </div>
    </div>
  </div>
</div>

<script>
const voiceList = document.getElementById("voice");
const alertsList = document.getElementById("alerts");
const movesList = document.getElementById("moves");
const voiceN = document.getElementById("voice-n");
const alertsN = document.getElementById("alerts-n");
const movesN = document.getElementById("moves-n");
let voiceCount = 0, alertsCount = 0, movesCount = 0;

function nowStr(){return new Date().toLocaleTimeString("en-GB",{hour12:false})}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c])}
function row(cls,tick,html){
  const d=document.createElement("div");
  d.className="row "+cls;
  const tk=(tick!==undefined&&tick!==null)?`t${tick}`:"";
  d.innerHTML=`<span class="t">${nowStr()} ${tk}</span>${html}`;
  return d;
}
function addVoice(who,text,tick){
  voiceList.prepend(row("voice",tick,`<span class="who">${who}:</span>"${esc(text)}"`));
  voiceCount++;voiceN.textContent=voiceCount;
  document.getElementById("cue-panel").textContent=`> ${who}: ${text}_`;
}
function addAlert(code,msg,flash){
  const d=row("alert",null,`<b>${esc(code)}</b> · ${esc(msg)}`);
  if(flash) d.classList.add("flash");
  alertsList.prepend(d);alertsCount++;alertsN.textContent=alertsCount;
}
function addMove(cls,tick,html,prebaked){
  const d=row(cls,tick,html);
  if(prebaked) d.classList.add("prebaked");
  movesList.prepend(d);movesCount++;movesN.textContent=movesCount;
  while(movesList.children.length>120) movesList.lastChild.remove();
}
function setState(kind,label){
  const d=document.getElementById("state-dot");
  d.className="dot "+kind;
  document.getElementById("state-text").textContent=label;
}
function fmtM(x){return (x>=0?"+":"")+(+x).toFixed(2)+"m"}
function fmtRad(x){const d=x*180/Math.PI;return (d>=0?"left ":"right ")+Math.abs(d).toFixed(0)+"°"}

// Plan decomposition state
let planCue=null, planSteps=[], planIdx=0;
function renderPlan(){
  const sel=document.getElementById("plan-steps");
  document.getElementById("plan-cue").textContent = planCue?`> ${planCue}_`:"— no active plan —";
  document.getElementById("plan-progress-tag").textContent = planSteps.length?`${Math.min(planIdx+1,planSteps.length)}/${planSteps.length}`:"—";
  sel.innerHTML="";
  planSteps.forEach((s,i)=>{
    const e=document.createElement("div");
    e.className="plan-step"+(i===planIdx?" active":"")+(i<planIdx?" done":"");
    const text = (typeof s==="string")?s:(s.text||"");
    const pre = (typeof s==="object"&&s!==null&&s.tool);
    e.innerHTML = `<span class="idx">${String(i+1).padStart(2,"0")}.</span>
                   <span class="txt">${esc(text)}</span>
                   <span class="val ${pre?'pre':'llm'}">${pre?'pre-baked':'llm'}</span>`;
    sel.appendChild(e);
  });
  // validation line
  const v = document.getElementById("plan-validation");
  if(!planSteps.length){ v.textContent=""; }
  else {
    const baked = planSteps.filter(s => typeof s==="object" && s && s.tool).length;
    v.textContent = `${baked}/${planSteps.length} pre-baked`;
  }
}
function clearPlan(){planCue=null;planSteps=[];planIdx=0;renderPlan()}

// Rolling latencies
const vlmMs=[], plannerMs=[];
function pushRoll(arr,v){arr.push(v);while(arr.length>5) arr.shift()}
function mean(a){return a.length?Math.round(a.reduce((x,y)=>x+y,0)/a.length):null}

function handle(r){
  if(r.kind==="start"){
    setState("idle","awaiting cue");
    vlmMs.length=0;plannerMs.length=0;clearPlan();
  } else if(r.kind==="model_info"){
    document.getElementById("llm-model").textContent=r.llm_model;
    document.getElementById("llm-host").textContent=r.llm_host;
    document.getElementById("vlm-model").textContent=r.vlm_model;
    document.getElementById("vlm-host").textContent=r.vlm_host;
    document.getElementById("env-tag").textContent=r.llm_host;
  } else if(r.kind==="status"){
    if(r.state==="vlm_thinking") setState("vlm",`VLM thinking (t${r.tick})`);
    else if(r.state==="vlm_done"){document.getElementById("vlm-ms").textContent=r.ms+" ms";pushRoll(vlmMs,r.ms);setState("idle","VLM done")}
    else if(r.state==="planner_thinking") setState("planner",`Planner thinking (t${r.tick})`);
    else if(r.state==="planner_done"){document.getElementById("planner-ms").textContent=r.ms+" ms";pushRoll(plannerMs,r.ms);setState("acting","acting")}
    else if(r.state==="vlm_error"||r.state==="planner_error") setState("error",r.state);
    const mv=mean(vlmMs), mp=mean(plannerMs);
    if(mv||mp) document.getElementById("mean-ms").textContent=`mean V ${mv??"—"}ms · P ${mp??"—"}ms`;
  } else if(r.kind==="idle"){
    setState("idle","idle — awaiting voice cue");
  } else if(r.kind==="stop"){
    const cls = r.success?"ok":"alert";
    const d = row(cls,null,`<b>${r.success?"PASS":"FAIL"}</b> ${esc(r.reason||"")}`);
    alertsList.prepend(d);alertsCount++;alertsN.textContent=alertsCount;
  } else if(r.kind==="live_cue"){
    addVoice("you (mic)", r.text, r.tick);
  } else if(r.kind==="action"){
    const c=r.call||{}; const a=c.args||{}; const name=c.name; const tick=r.tick;
    const prebaked = r.source === "pre-baked";
    if(name==="move"){
      const parts=[];
      if(a.dx) parts.push(`forward ${fmtM(a.dx)}`);
      if(a.dy) parts.push(`side ${fmtM(a.dy)}`);
      const hasTurn=a.dtheta&&Math.abs(a.dtheta)>0.001;
      if(hasTurn) parts.push(`turn ${fmtRad(a.dtheta)}`);
      const label=parts.length?parts.join(", "):"no-op move";
      addMove(hasTurn&&parts.length===1?"turn":"move",tick,`${label}${c.rationale?` <span class="mini">— ${esc(c.rationale)}</span>`:""}`,prebaked);
    } else if(name==="grasp"||name==="release"){
      addMove("grip",tick,`${name} gripper`,prebaked);
    } else if(name==="emote"){
      addMove("emote",tick,`emote <b>${esc(a.label||"")}</b>`,prebaked);
    } else if(name==="speak"){
      addMove("speak",tick,`speak: "${esc(a.text||"")}"`,prebaked);
    } else {
      addMove("move",tick,`${name||"?"} ${esc(JSON.stringify(a))}`,prebaked);
    }
    if(!(r.result&&r.result.ok)){
      addAlert("action-failed",`t${tick} ${name} -> ${JSON.stringify(r.result||{})}`);
    }
  } else if(r.kind==="clamp_summary"){
    addAlert("move-clamped",`${r.count} move() calls were clamped by world bounds`);
  } else if(r.kind==="alert"){
    // Only show real errors/problems. No plan_installed/plan_complete noise.
    const flash = ["cue-not-understood","cue-decompose-failed","step-direction-mismatch","step-abandoned","action-failed"].includes(r.code);
    addAlert(r.code||"alert",`t${r.tick??"?"} ${r.message||""}`,flash);
  } else if(r.kind==="plan_installed"){
    planCue=r.cue; planSteps=r.steps||[]; planIdx=0; renderPlan();
  } else if(r.kind==="plan_progress"){
    planIdx=r.step_index; renderPlan();
  } else if(r.kind==="plan_complete"){
    planIdx=planSteps.length; renderPlan();
    setTimeout(clearPlan, 4000);
  }
}

const es = new EventSource("/events");
es.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch {} };
setInterval(() => { document.getElementById("cam").src = "/camera.jpg?" + Date.now(); }, 500);

function sendCue(text){
  addVoice("you (typed)", text, null);
  fetch("/cue",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({text})}).catch(()=>{});
}
const txt=document.getElementById("txt");
txt.addEventListener("keydown",e=>{if(e.key==="Enter"&&txt.value.trim()){sendCue(txt.value.trim());txt.value=""}});

const micBtn=document.getElementById("mic");
const micStatus=document.getElementById("mic-status");
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
let recog=null, recording=false;
if(!SR){micBtn.disabled=true;micStatus.textContent="SpeechRecognition unavailable (use Chrome/Safari)"}
else {
  recog=new SR(); recog.lang="en-US"; recog.interimResults=false; recog.continuous=false;
  recog.onresult=(e)=>{const text=e.results[0][0].transcript.trim();micStatus.textContent="sent: "+text;addVoice("you (mic)",text,null);fetch("/cue",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({text})}).catch(()=>{})};
  recog.onend=()=>{recording=false;micBtn.textContent="> mic off";micBtn.classList.remove("rec")};
  recog.onerror=(e)=>{micStatus.textContent="error: "+e.error};
  micBtn.onclick=()=>{if(recording){recog.stop();return}recording=true;micBtn.textContent="> listening…";micBtn.classList.add("rec");micStatus.textContent="speak now";try{recog.start()}catch(err){micStatus.textContent=err.message}};
}
</script>
</body></html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return REHEARSAL_HTML


@app.post("/cue")
async def post_cue(req: Request) -> JSONResponse:
    """Append a live voice cue (text) that the rehearsal runner will consume on its next tick."""
    try:
        data = await req.json()
    except Exception:
        data = {}
    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
    LIVE_CUES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LIVE_CUES_PATH.open("a") as f:
        f.write(_json.dumps({"ts": _time.time(), "text": text}) + "\n")
    return JSONResponse({"ok": True, "text": text})
