const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const esc = escapeHtml;
let state = {assets:[],cases:[],suites:[],runs:[]}, selectedRun = null, activeCase = null;
let activeVision = null;
const terminal = new Set(['completed','partial','failed','canceled']);
const pageTitles = {overview:'Overview',perception:'Real-data lab',videos:'Real-video lab',suites:'Scenario suites',runs:'Evaluation runs',cases:'Evidence library',compare:'Compare runs',settings:'Setup & requirements'};

async function api(path, options={}) {
  const response = await fetch('/v1'+path, {...options, headers:{'Content-Type':'application/json','X-CheckoutCheck':'local',...options.headers}});
  if (!response.ok) {const error = await response.json().catch(()=>({detail:response.statusText}));throw new Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail));}
  return response.json();
}
const post = (path, data) => api(path, {method:'POST',body:JSON.stringify(data)});
function notify(message, error=false) {const node=$('#notice');node.className=error?'error':'success';node.textContent=message;node.hidden=false;}
function empty(title, text, action='', label='') {return `<div class="empty"><span class="empty-symbol">▧</span><h3>${esc(title)}</h3><p>${esc(text)}</p>${action?`<button class="secondary" data-action="${action}">${esc(label)}</button>`:''}</div>`;}
function badge(status) {return `<span class="badge ${status==='completed'?'good':['failed','canceled'].includes(status)?'bad':status==='partial'?'warn':''}">${esc(status.replaceAll('_',' '))}</span>`;}
function stat(label,value,note) {return `<div class="stat"><div class="stat-label">${esc(label)}<span>↗</span></div><div class="stat-value">${esc(value)}</div><small>${esc(note)}</small></div>`;}
function metric(label, item) {return stat(label,item.value===null?'N/A':`${Math.round(item.value*1000)/10}%`,`${item.numerator} / ${item.denominator} eligible cases`);}
function suiteName(id) {return state.suites.find(s=>s.id===id)?.name||id.slice(0,8);}
function runTable(runs) {
  if(!runs.length) return empty('No evaluations yet','Run a reviewed suite or import predictions. Results will appear here after actual processing.','run','Create an evaluation');
  return `<div class="table-scroll"><table><thead><tr><th>Evaluation</th><th>Suite</th><th>Status</th><th>Created</th><th></th></tr></thead><tbody>${runs.map(r=>`<tr><td><button class="row-link" data-run="${esc(r.id)}">Run ${esc(r.id.slice(0,8))}</button><small>${r.progress} cases processed</small></td><td>${esc(suiteName(r.suite_id))}</td><td>${badge(r.status)}</td><td>${new Date(r.created*1000).toLocaleString()}</td><td><button class="row-link" data-run="${esc(r.id)}">Inspect →</button></td></tr>`).join('')}</tbody></table></div>`;
}
function route() {
  const page = location.hash.slice(1) || 'overview';
  const selected = state.runtime?.read_only && !['perception','videos','settings'].includes(page) ? 'perception' : pageTitles[page] ? page : 'overview';
  document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!==selected);
  document.querySelectorAll('[data-page]').forEach(el=>{el.classList.toggle('active',el.dataset.page===selected);if(el.dataset.page===selected)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  $('#breadcrumb').textContent=pageTitles[selected];
}
function render() {
  const reviewOnly = state.runtime?.read_only === true;
  const cloud = reviewOnly || state.runtime?.mode === 'aws_private_single_operator';
  if(reviewOnly){
    document.querySelectorAll('button[data-action], [data-page="overview"], [data-page="suites"], [data-page="runs"], [data-page="cases"], [data-page="compare"]').forEach(node=>node.hidden=true);
    if(!location.hash)location.hash='perception';
  }
  $('#workspace-location').textContent = cloud ? 'AWS workspace' : 'Local workspace';
  $('#engine-location').textContent = cloud ? 'AWS engine' : 'Local engine';
  $('.environment').textContent = reviewOnly ? '◉ AWS judge demo · inspect measured results' : cloud ? '◉ Private AWS deployment' : '◉ Local development';
  const connection = state.runtime?.aws_connection;
  const checked = connection?.status === 'checked';
  $('#aws-sidebar-status').textContent = reviewOnly ? 'AWS · public review' : cloud ? 'Private EC2 · instance role' : checked ? 'AWS account checked · local engine' : 'AWS connection needs checking';
  $('#aws-connection-status').textContent = cloud ? 'EC2 instance role' : checked ? 'Connection checked' : 'Needs checking';
  $('#execution-status').textContent = cloud ? 'See measured AWS runs' : 'Local results';
  $('#aws-connection-detail').textContent = reviewOnly ? 'Public review of measured AWS results. Uploads and execution are available only in the private operator workspace.' : cloud ? 'Private AWS worker. Jobs execute here using original data; inspect completed runs for measured results. No browser or root credentials are stored in this container.' : connection?.checked_at ? `Account ending ${connection.account_suffix} · ${connection.region} · checked ${new Date(connection.checked_at).toLocaleString()}. This is a recorded connection check, not proof of current credentials or cloud execution.` : 'No AWS connection check recorded. The application runs locally.';

  $('#suite-count').textContent=state.suites.length;
  $('#overview-stats').innerHTML=stat('Scenario suites',state.suites.length,'Immutable evaluation versions')+stat('Evidence cases',state.cases.length,'Real recordings only')+stat('Completed runs',state.runs.filter(r=>r.status==='completed').length,'All submitted cases scored')+stat('Active evaluations',state.runs.filter(r=>!terminal.has(r.status)).length,'Single worker · sequential processing');
  $('#recent-runs').innerHTML=runTable(state.runs.slice(0,4));
  $('#run-list').innerHTML=runTable(state.runs);
  $('#suite-list').innerHTML=state.suites.length?`<div class="suite-grid">${state.suites.map(s=>`<article class="panel suite-card"><span class="tag">FROZEN · TRACK ${esc(s.suite.input_track)}</span><h2>${esc(s.name)}</h2><p>${s.entries.length} reviewed cases · ${esc(s.suite.evidence_kind)} recordings<br>${[...new Set(s.entries.map(e=>e.annotation.split))].map(esc).join(' · ')}</p><div class="hash mono">SHA-256 ${esc(s.hash)}</div><div class="actions"><button class="primary" data-evaluate="${esc(s.id)}">▷ Evaluate suite</button><button class="secondary" data-download-suite="${esc(s.id)}">Manifest ↓</button></div></article>`).join('')}</div>`:`<div class="panel">${empty('Build your first scenario suite','Add real recordings and review their annotations before freezing a suite. Suite hashes bind media, scan events, configuration, and labels.','ingest','Add a recording')}</div>`;
  $('#case-list').innerHTML=state.cases.length?`<div class="panel table-scroll"><table><thead><tr><th>Case</th><th>Transaction truth</th><th>Visibility</th><th>Review</th><th>Split</th></tr></thead><tbody>${state.cases.map(c=>`<tr><td><button class="row-link" data-case="${esc(c.id)}">${esc(c.title)}</button><small>${esc(c.id)}</small></td><td>${esc(c.annotation.truth)}</td><td>${esc(c.annotation.visibility)}</td><td>${badge(c.annotation.review_status)}</td><td>${esc(c.annotation.split)}</td></tr>`).join('')}</tbody></table></div>`:`<div class="panel">${empty('Your evidence library is empty','No generated clips or invented results. Add a real recording, a synchronized transaction log, and independently reviewed annotations.','ingest','Import real footage')}</div>`;
  for(const id of ['baseline','candidate']) {const node=$('#'+id), value=node.value;node.innerHTML='<option value="">Choose a scored run</option>'+state.runs.filter(r=>['completed','partial'].includes(r.status)).map(r=>`<option value="${esc(r.id)}">${esc(suiteName(r.suite_id))} · ${esc(r.id.slice(0,8))}</option>`).join('');node.value=value;}
}
async function refresh() {state=await api('/state');render();route();}
function modal(title, html, handler) {
  $('#modal-title').textContent=title;$('#modal-body').innerHTML=`<div class="modal-content"><div id="form-error" class="error" hidden></div>${html}</div>`;
  if(!$('#modal').open)$('#modal').showModal();
  const form=$('#modal form');if(form&&handler)form.addEventListener('submit',async event=>{event.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;$('#form-error').hidden=true;try{await handler(new FormData(form));}catch(error){$('#form-error').textContent=error.message;$('#form-error').hidden=false;}finally{button.disabled=false;}});
}
function closeModal() {$('#modal').close();}
function download(name,value) {const link=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

function ingest() {
  modal('Add real checkout evidence',`<p class="help">Import a real recording and its actual mock transaction events. The built-in vision adapter requires visible ArUco product markers. Reference annotations remain separate from inference inputs.</p><form id="ingest-form">
    <label>Real checkout video<input name="video" type="file" accept="video/mp4,.mp4" required><small>MP4 · up to 60 seconds · 250 MB · 1920 × 1080</small></label>
    <label>Case title<input name="title" placeholder="Describe the recorded interaction" required maxlength="200"></label>
    <div class="form-grid"><label>Case ID<input name="id" required maxlength="200" placeholder="Your unique case identifier"></label><label>Family ID<input name="family_id" required maxlength="200" placeholder="Group matched variations together"></label><label>Recording session ID<input name="session_id" required maxlength="200"></label><label>Split<select name="split"><option value="development">Development</option><option value="calibration">Calibration</option><option value="holdout">Holdout</option></select></label></div>
    <h3>Permitted inference inputs</h3><label>Product marker catalog (JSON object)<textarea name="catalog" required placeholder='Map each marker ID string to its SKU. Use a distinct marker for each product instance.'></textarea><small>Marker dictionary: DICT_4X4_50. IDs 0–49; values are your SKU identifiers.</small></label>
    <label>Import a recorded scan log<input id="scan-log-file" type="file" accept=".json,.csv,application/json,text/csv"><small>JSON or CSV · maximum 1 MB. CSV columns: id,type,t_ms,sku,quantity,scan_id. Timestamps are milliseconds.</small></label><button type="button" class="secondary" id="validate-scan-log">Validate supplied scan log</button><p id="scan-log-validation" class="help" role="status"></p>
    <label>Transaction events (JSON array)<textarea name="events" required placeholder="Paste your ordered mock transaction event records"></textarea><small>Each event: id, type, t_ms. scan_add also requires sku and quantity. scan_void requires scan_id. End with payment_complete. Timestamps are milliseconds.</small></label>
    <div class="form-grid"><label>Clock offset (ms)<input type="number" name="offset_ms" value="0" min="-60000" max="60000" required><small>Video time = event time + offset.</small></label><label>Bagging boundary (0–1)<input type="number" name="bagging_x" value="0.6" min="0.1" max="0.9" step="0.01" required><small>Right side of the frame is the bagging zone.</small></label></div>
    <h3>Independent reference annotation</h3><div class="form-grid"><label>Transaction truth<select name="truth"><option value="balanced">Balanced</option><option value="discrepancy">Discrepancy</option><option value="unresolved">Unresolved</option></select></label><label>Visual observability<select name="visibility"><option value="sufficient">Sufficient</option><option value="partial">Partial</option><option value="insufficient">Insufficient</option></select></label><label>Review status<select name="review_status"><option value="draft">Draft</option><option value="reviewed">Reviewed</option><option value="adjudicated">Adjudicated</option><option value="disputed">Disputed</option></select></label><label>Pair ID (optional)<input name="pair_id" maxlength="200"><small>Both reviewed members must be in the same suite.</small></label></div>
    <label>Reference discrepancy windows (JSON array)<textarea name="discrepancies" required>[]</textarea><small>For known discrepancies, each window needs id, sku, start_ms, end_ms in video time. Leave [] for balanced transactions. Never infer these labels from model output.</small></label>
    <label><input type="checkbox" name="requires_abstention">Reference policy requires abstention given the permitted inputs</label>
    <label><input type="checkbox" name="input_valid" checked>Clock alignment and input integrity have been checked</label>
    <label><input type="checkbox" name="rights_valid" required>I have permission to use this real recording for private evaluation</label>
    <button class="primary" type="submit">Validate & add evidence →</button><p class="help">No public publication. Data is stored locally in private-data/.</p></form>`,async form=>{
      if(logText!==null)throw new Error('Validate the selected scan log before importing the recording.');
      const inputs={events:JSON.parse(form.get('events')),catalog:JSON.parse(form.get('catalog')),offset_ms:Number(form.get('offset_ms')),bagging_x:Number(form.get('bagging_x')),min_observations:3};
      const annotation=Object.fromEntries(['id','family_id','session_id','split','truth','visibility','review_status'].map(k=>[k,form.get(k)]));
      Object.assign(annotation,{rights_valid:form.has('rights_valid'),input_valid:form.has('input_valid'),requires_abstention:form.has('requires_abstention'),discrepancies:JSON.parse(form.get('discrepancies'))});
      if(form.get('pair_id'))annotation.pair_id=form.get('pair_id');
      const asset=await api('/assets',{method:'POST',headers:{'Content-Type':'video/mp4'},body:form.get('video')});
      await post('/cases',{asset_id:asset.id,title:form.get('title'),annotation,inputs});closeModal();await refresh();location.hash='cases';notify('Real recording validated and added. Review its annotation before freezing a suite.');
    });
  let logFormat='json',logText=null;
  $('#scan-log-file').addEventListener('change',async event=>{
    const file=event.target.files[0];if(!file)return;
    if(file.size>1000000){$('#scan-log-validation').textContent='Scan log exceeds 1 MB.';event.target.value='';return;}
    logFormat=file.name.toLowerCase().endsWith('.csv')?'csv':'json';logText=await file.text();
    $('#scan-log-validation').textContent='File loaded. Enter the catalog and clock offset, then validate.';
  });
  $('#validate-scan-log').addEventListener('click',async()=>{
    const button=$('#validate-scan-log');button.disabled=true;
    try{
      const form=new FormData($('#ingest-form'));
      const result=await post('/scan-logs/validate',{content:logText??form.get('events'),format:logText===null?'json':logFormat,inputs:{catalog:JSON.parse(form.get('catalog')),offset_ms:Number(form.get('offset_ms')),bagging_x:Number(form.get('bagging_x')),min_observations:3}});
      $('#ingest-form [name=events]').value=JSON.stringify(result.events,null,2);logText=null;
      $('#scan-log-validation').textContent=`${result.event_count} events validated; payment at ${(result.payment_video_ms/1000).toFixed(3)} s in video time. Net scans: ${JSON.stringify(result.net_scan_counts)}. Independently review physical inventory.`;
    }catch(error){$('#scan-log-validation').textContent=error.message;}finally{button.disabled=false;}
  });
}
function freeze() {
  const eligible=state.cases.filter(c=>['reviewed','adjudicated'].includes(c.annotation.review_status));
  if(!eligible.length){modal('Freeze a suite',empty('Reviewed evidence is required','Add recordings with reviewed or adjudicated annotations first. Draft and disputed labels cannot enter a frozen suite.'));return;}
  modal('Freeze a reviewed suite',`<form><label>Suite name<input name="name" required maxlength="200" placeholder="Name this evaluation version"></label><div class="check-list">${eligible.map(c=>`<label><input type="checkbox" name="cases" value="${esc(c.id)}">${esc(c.title)} <small>${esc(c.annotation.split)} · ${esc(c.annotation.family_id)}</small></label>`).join('')}</div><div class="form-grid"><label>Matching tolerance (ms)<input name="tolerance" type="number" min="0" max="10000" value="1000" required></label><label>Alert cooldown (ms)<input name="cooldown" type="number" min="0" max="10000" value="2000" required></label></div><label><input type="checkbox" name="abstention" checked>Route abstentions to neutral human review</label><p class="help">This creates an immutable snapshot. Family and recording-session leakage across splits is rejected. Corrections require new case IDs and a new suite.</p><button class="primary" type="submit">Freeze suite →</button></form>`,async form=>{await post('/suites',{name:form.get('name'),case_ids:form.getAll('cases'),policy:{tolerance_ms:Number(form.get('tolerance')),cooldown_ms:Number(form.get('cooldown')),abstention_routes_to_review:form.has('abstention')}});closeModal();await refresh();location.hash='suites';notify('Suite frozen with hashes of its evidence and annotations.');});
}
function runModal(suiteId='') {
  if(!state.suites.length){modal('New evaluation',empty('Freeze a suite first','Runs require a reviewed, immutable suite. Add real evidence, then freeze a suite.'));return;}
  modal('Start an evaluation',`<form><label>Frozen suite<select name="suite_id">${state.suites.map(s=>`<option value="${esc(s.id)}" ${s.id===suiteId?'selected':''}>${esc(s.name)} · ${s.entries.length} cases</option>`).join('')}</select></label><label>Execution mode<select name="mode" id="run-mode"><option value="vision">Run OpenCV 5 marker baseline</option><option value="import">Import external predictions</option></select></label><div id="prediction-input" hidden><label>Prediction bundle (JSON)<textarea name="predictions" placeholder="Paste the prediction bundle for this exact suite hash"></textarea></label><p class="help">Required: schema_version, suite_hash, input_track, model {id, version, config, provenance}, predictions [{case_id, decision, events}]. Alert events require id, sku, t_ms. Imported inference is unverified.</p></div><div class="callout">The built-in adapter supports marker-instrumented real recordings only. It cannot evaluate arbitrary unmarked retail footage. Incomplete tracking produces abstention, not a confident conclusion.</div><button class="primary" type="submit">Queue evaluation →</button></form>`,async form=>{const request={suite_id:form.get('suite_id'),idempotency_key:crypto.randomUUID()};if(form.get('mode')==='import')request.imported=JSON.parse(form.get('predictions'));const result=await post('/runs',request);closeModal();await refresh();location.hash='runs';await inspectRun(result.id);});
  $('#run-mode').addEventListener('change',e=>$('#prediction-input').hidden=e.target.value!=='import');
}
async function inspectRun(id, scroll=true) {
  selectedRun=id;const run=await api('/runs/'+encodeURIComponent(id));if(selectedRun!==id)return;
  location.hash='runs';let html=`<section class="panel detail-panel"><div class="detail-actions"><h2>Run ${esc(id.slice(0,8))}</h2>${badge(run.status)}${!terminal.has(run.status)?`<button class="secondary" data-cancel="${esc(id)}">Cancel run</button>`:''}${run.result?`<a href="/v1/runs/${esc(id)}/export">Download reproducible scoring bundle ↓</a>`:''}</div><p class="help">${esc(suiteName(run.suite_id))} · Last update ${new Date(run.updated*1000).toLocaleString()}</p>`;
  if(run.error)html+=`<div class="error">${esc(run.error)}</div>`;
  if(!run.result)html+=`<progress max="${state.suites.find(s=>s.id===run.suite_id)?.entries.length||1}" value="${run.progress}"></progress><p class="help">${run.progress} cases processed. Results appear after scoring; incomplete work is never counted as success.</p>`;
  else {
    const report=run.result.report, m=report.metrics;
    html+=`<div class="stat-grid">${metric('False alert rate',m.false_alert_rate)}${metric('Discrepancy recall',m.discrepancy_recall)}${metric('Intervention burden',m.intervention_burden)}${metric('Processing coverage',m.processing_coverage)}</div><div class="callout">${run.result.execution.inference_executed?'Executed locally with the marker instrumentation baseline.':'External predictions imported; inference has not been verified.'} Counts describe this suite only. They do not establish real-world fairness or accessibility.</div><div class="table-scroll"><table><thead><tr><th>Case</th><th>Decision</th><th>Findings / exclusions</th><th>Matched events</th></tr></thead><tbody>${report.cases.map(c=>`<tr><td><button class="row-link" data-evidence="${esc(c.case_id)}" data-evidence-run="${esc(id)}">${esc(state.cases.find(x=>x.id===c.case_id)?.title||c.case_id)} →</button></td><td>${esc(c.decision||'Not scored')}</td><td>${esc(c.exclusions.length?c.exclusions.join(', '):c.findings.join(', ')||'No scored error')}</td><td>${c.matches?.length??'—'} / ${c.reference_event_count??'—'}</td></tr>`).join('')}</tbody></table></div><details><summary class="help">All metrics, exclusions, and provenance</summary><pre>${esc(JSON.stringify({metrics:m,by_split:report.by_split,by_visibility:report.by_visibility,failures:run.result.failures,execution:run.result.execution},null,2))}</pre></details>`;
  }
  $('#run-detail').innerHTML=html+'</section>';if(scroll)$('#run-detail').scrollIntoView({behavior:'smooth',block:'start'});
}
async function inspectCase(id, runId=null) {
  const entry=state.cases.find(c=>c.id===id);if(!entry)return;
  activeCase=id;activeVision=null;let finding=null,predictedEvents=[];
  if(runId){const run=await api('/runs/'+encodeURIComponent(runId));activeVision=run.result?.vision?.[id];finding=run.result?.report.cases.find(c=>c.case_id===id);predictedEvents=run.result?.predictions?.predictions?.find(p=>p.case_id===id)?.events||[];}
  const events=evidenceTimeline(entry,predictedEvents,finding?.matches||[]);
  $('#case-detail').innerHTML=`<section class="panel detail-panel"><h2>${esc(entry.title)}</h2><p class="help">Reference: ${esc(entry.annotation.truth)} · Visibility: ${esc(entry.annotation.visibility)} · ${esc(entry.annotation.review_status)}</p>${finding?`<div class="callout">Model decision: ${esc(finding.decision||'Unscored')}. ${esc(finding.findings.join(', ')||'No scored error')}${activeVision?.warnings.length?' · '+esc(activeVision.warnings.join('; ')):''}</div>`:''}<div class="video-layout"><div><div class="video-wrap"><video id="evidence-video" src="/v1/media/${esc(entry.asset_id)}" controls preload="metadata" aria-label="Original checkout recording"></video><canvas id="overlay" aria-label="Detected product marker overlays"></canvas></div><p class="help">Original recording. Overlays show model observations, not reference annotations. Event buttons seek in video time.</p><div id="video-warning" class="error" hidden></div></div><div class="event-list"><h3>Synchronized event table</h3>${events.map(e=>`<button class="event-button" data-seek="${e.t_ms}"><time>${(e.t_ms/1000).toFixed(2)}s</time>${esc(e.label)}</button>`).join('')}</div></div>${activeVision?`<details><summary class="help">Vision evidence and review-controller trace</summary><pre>${esc(JSON.stringify({tracks:activeVision.tracks,observed_counts:activeVision.observed_counts,scan_counts:activeVision.scan_counts,trace:activeVision.controller_trace,warnings:activeVision.warnings,runtime_seconds:activeVision.runtime_seconds,opencv_version:activeVision.metadata.opencv_version},null,2))}</pre></details>`:''}<p class="mono">Media SHA-256: ${esc(entry.asset_sha256)}</p></section>`;
  const video=$('#evidence-video');video.addEventListener('timeupdate',drawOverlay);video.addEventListener('loadedmetadata',drawOverlay);video.addEventListener('error',()=>{const message=$('#video-warning');message.textContent='This browser could not decode the uploaded video codec. Keep the original evidence and re-encode to H.264 MP4 with a verified timestamp mapping before importing a new case.';message.hidden=false;});
  location.hash='cases';$('#case-detail').scrollIntoView({behavior:'smooth'});
}
function drawOverlay() {
  const video=$('#evidence-video'),canvas=$('#overlay');if(!video||!canvas)return;
  canvas.width=video.videoWidth||640;canvas.height=video.videoHeight||360;const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
  const items=activeVision?.evidence||[];const time=video.currentTime*1000;const closest=items.reduce((best,e)=>Math.abs(e.t_ms-time)<Math.abs(best-time)?e.t_ms:best,Infinity);
  if(Math.abs(closest-time)>250)return;
  for(const e of items.filter(e=>e.t_ms===closest)){ctx.strokeStyle='#a5df81';ctx.fillStyle='#a5df81';ctx.lineWidth=2;const [x1,y1,x2,y2]=e.box;ctx.strokeRect(x1*canvas.width,y1*canvas.height,(x2-x1)*canvas.width,(y2-y1)*canvas.height);ctx.font='14px sans-serif';ctx.fillText(`${e.sku} · marker ${e.marker}`,x1*canvas.width,Math.max(15,y1*canvas.height-7));}
}
document.addEventListener('click',async event=>{const node=event.target.closest('button');if(!node)return;try{
  if(node.dataset.action==='ingest')ingest();if(node.dataset.action==='freeze')freeze();if(node.dataset.action==='run')runModal();
  if(node.dataset.evaluate)runModal(node.dataset.evaluate);
  if(node.dataset.run)await inspectRun(node.dataset.run);
  if(node.dataset.case)await inspectCase(node.dataset.case);
  if(node.dataset.evidence)await inspectCase(node.dataset.evidence,node.dataset.evidenceRun);
  if(node.dataset.seek){$('#evidence-video').currentTime=Number(node.dataset.seek)/1000;drawOverlay();}
  if(node.dataset.cancel){await post('/runs/'+node.dataset.cancel+'/cancel',{});await refresh();await inspectRun(node.dataset.cancel,false);}
  if(node.dataset.downloadSuite){const suite=state.suites.find(s=>s.id===node.dataset.downloadSuite);download('checkoutcheck-suite.json',suite.suite);}
}catch(error){notify(error.message,true);}});
$('#close-modal').addEventListener('click',closeModal);
$('#compare-form').addEventListener('submit',async event=>{event.preventDefault();try{const result=await post('/comparisons',{baseline:$('#baseline').value,candidate:$('#candidate').value});$('#comparison-result').innerHTML=`<section class="panel detail-panel"><h2>Comparison results</h2><p class="help">A changed decision is not automatically an improvement. Review alert burden, misses, and abstentions together.</p><div class="table-scroll"><table><thead><tr><th>Metric</th><th>Baseline</th><th>Candidate</th></tr></thead><tbody>${['false_alert_rate','discrepancy_recall','intervention_burden','abstention_rate','processing_coverage'].map(k=>`<tr><td>${esc(k.replaceAll('_',' '))}</td>${[result.baseline,result.candidate].map(r=>`<td>${r.metrics[k].numerator} / ${r.metrics[k].denominator}${r.metrics[k].value===null?' · N/A':''}</td>`).join('')}</tr>`).join('')}</tbody></table><table><thead><tr><th>Case</th><th>Change</th><th>Baseline</th><th>Candidate</th></tr></thead><tbody>${result.changes.map(c=>`<tr><td>${esc(c.case_id)}</td><td>${badge(c.state)}</td><td>${esc(c.before.decision||'Unscored')}</td><td>${esc(c.after.decision||'Unscored')}</td></tr>`).join('')}</tbody></table></div></section>`;}catch(error){notify(error.message,true);}});
window.addEventListener('hashchange',route);route();refresh().catch(error=>notify(error.message,true));
setInterval(async()=>{if(document.hidden)return;try{if(state.runs.some(r=>!terminal.has(r.status))){await refresh();if(selectedRun&&location.hash==='#runs')await inspectRun(selectedRun,false);}}catch(error){notify(error.message,true);}},2000);
