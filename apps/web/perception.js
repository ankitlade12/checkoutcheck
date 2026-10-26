/* Original RPC photographs; image metrics remain separate from transaction metrics. */
let perceptionState = {runs:[]}, perceptionRun = null;
const percent = value => value == null ? 'N/A' : `${(100*value).toFixed(1)}%`;
async function refreshPerception() {
  perceptionState = await api('/perception');
  const data = perceptionState, manifest = data.manifest;
  if (!data.available) {
    $('#perception-content').innerHTML = empty('Install the real RPC subset','Run .venv/bin/python -m checkoutcheck.rpc --count 24 --references 2 from the project folder. This downloads original photographs from the publisher.');
    return;
  }
  const selection = $('#perception-model')?.value;
  $('#perception-content').innerHTML = `
    <div class="stat-grid">${stat('Validation photographs',manifest.images.length,'Fixed exploratory subset · 8 per difficulty')}${stat('Annotated products',manifest.images.reduce((n,e)=>n+e.annotations.length,0),'Publisher reference annotations')}${stat('Training references',data.reference_bank?.images||0,'Separate original training photographs')}${stat('Product categories',manifest.categories.length,'RPC catalog')}</div>
    <div class="panel detail-panel"><h2>A real-image perception benchmark</h2><p>Original photographs from <a href="https://rpc-dataset.github.io/" target="_blank" rel="noreferrer">RPC · Wei et al.</a>, distributed under <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noreferrer">CC BY-NC-SA 4.0</a> for noncommercial use. Every downloaded image is checksummed. No generated imagery or invented transaction events.</p><div class="callout">This is an exploratory validation sample, not a final holdout. These images have no payment or scan logs. Object detection results do not measure checkout discrepancies or unnecessary interventions.</div>
    <div class="actions"><label>Perception method<select id="perception-model">${Object.entries(data.models).map(([id,m])=>`<option value="${esc(id)}" ${(m.requires_references&&!data.reference_bank)||m.available===false?'disabled':''}>${esc(m.name)}</option>`).join('')}</select></label><button class="primary" id="start-perception">Run on all ${manifest.images.length} images →</button></div><p class="help">SIFT matches local image features to real training examples and estimates SKU identity. Foreground components and watershed only locate regions. Faster R-CNN adds photo-trained neural localization. All methods are experimental; poor results remain visible.</p><details><summary>Dataset identity and selection</summary><pre>${esc(JSON.stringify({dataset_hash:manifest.hash,selection:manifest.selection,reference_bank:data.reference_bank},null,2))}</pre></details></div>
    <div class="panel detail-panel"><h2>Measured runs</h2>${data.runs.length?`<div class="table-scroll"><table><thead><tr><th>Method</th><th>Status</th><th>Run</th><th></th></tr></thead><tbody>${data.runs.map(r=>`<tr><td>${esc(data.models[r.model]?.name||r.model)}</td><td>${badge(r.status)}</td><td>${esc(r.id.slice(0,8))}</td><td><button class="row-link" data-perception-run="${esc(r.id)}">Inspect results →</button></td></tr>`).join('')}</tbody></table></div>`:empty('No measured runs yet','Choose a method above to execute inference locally.')}</div>
    <div class="panel detail-panel"><h2>Original photographs</h2><p class="help">Select an image to inspect publisher annotations. Inspect a scored run first to also see its predictions.</p><div class="photo-grid">${manifest.images.map(e=>`<button class="photo-card" data-perception-image="${e.id}"><img src="/v1/perception/images/${e.id}" alt="RPC original checkout photograph ${esc(e.file_name)}" loading="lazy" width="1850" height="1850"><span>${esc(e.file_name)}</span><small>${esc(e.level)} · ${e.annotations.length} annotated products</small></button>`).join('')}</div></div>`;
  $('#perception-model').value = selection || (data.models['fasterrcnn-rpc-v1']?.available?'fasterrcnn-rpc-v1':data.reference_bank?'sift-reference-v1':'foreground-components-v1');
}

async function inspectPerception(id, scroll=true) {
  const run = await api('/runs/'+encodeURIComponent(id));
  perceptionRun = run;
  const result = run.result, m = result?.report.metrics;
  let html = `<section class="panel detail-panel"><div class="detail-actions"><h2>${esc(perceptionState.models?.[run.data.model]?.name||run.data.model)}</h2>${badge(run.status)}${!terminal.has(run.status)?`<button class="secondary" data-perception-cancel="${esc(id)}">Cancel run</button>`:''}${result?`<a href="/v1/runs/${esc(id)}/export">Export scoring evidence ↓</a>`:''}</div>`;
  if(run.error) html+=`<p class="error">${esc(run.error)}</p>`;
  if(!result) html+='<p class="help">The local worker loads original photographs and executes OpenCV. Results appear when scoring finishes; a failed job is never counted as success.</p>';
  else {
    html+=`<p class="help">IoU ≥ ${result.report.iou_threshold} · ${m.scored_images}/${m.submitted_images} images scored · ${result.execution.runtime_seconds.toFixed(1)} seconds · OpenCV ${esc(result.execution.opencv_version)}</p><div class="stat-grid">${stat('Localization precision',percent(m.precision),`${m.true_positive} matched / ${m.predicted_objects} predictions`)}${stat('Localization recall',percent(m.recall),`${m.true_positive} matched / ${m.reference_objects} reference objects`)}${stat('Count error (MAE)',m.count_mae?.toFixed(2)??'N/A','Average absolute error per image')}${stat('Exact image counts',`${m.exact_count_images}/${m.scored_images}`,`${m.excluded_images} images excluded`)}</div>`;
    if(m.sku_true_positive!==null)html+=`<div class="callout">SKU + location precision: <strong>${percent(m.sku_precision)}</strong> · recall: <strong>${percent(m.sku_recall)}</strong>. ${m.sku_true_positive} predictions match both product identity and location. Feature matches are not calibrated confidence scores.</div>`;
    html+=`<h3>Results by difficulty</h3><div class="table-scroll"><table><thead><tr><th>Difficulty</th><th>Coverage</th><th>Precision</th><th>Recall</th><th>Count MAE</th></tr></thead><tbody>${Object.entries(result.report.by_difficulty).map(([level,s])=>`<tr><td>${esc(level)}</td><td>${s.scored_images}/${s.submitted_images}</td><td>${percent(s.precision)}</td><td>${percent(s.recall)}</td><td>${s.count_mae?.toFixed(2)??'N/A'}</td></tr>`).join('')}</tbody></table></div>
    <h3>Inspect each image</h3><div class="table-scroll"><table><thead><tr><th>Image</th><th>Reference</th><th>Predicted</th><th>Matched</th><th>Missed</th></tr></thead><tbody>${result.report.cases.map(c=>`<tr><td><button class="row-link" data-perception-image="${c.image_id}">${esc(c.file_name)}</button></td><td>${c.reference_count}</td><td>${c.predicted_count??'Excluded'}</td><td>${c.true_positive??'—'}</td><td>${c.false_negative??'—'}</td></tr>`).join('')}</tbody></table></div><p class="help">${result.limitations.map(esc).join(' ')}</p><details><summary>Method configuration and failures</summary><pre>${esc(JSON.stringify({adapter:result.adapter,execution:result.execution,failures:result.failures},null,2))}</pre></details>
    <form id="perception-compare"><label>Compare this run with<select id="perception-other" required><option value="">Choose another scored run</option>${perceptionState.runs.filter(r=>r.id!==id&&['completed','partial'].includes(r.status)).map(r=>`<option value="${esc(r.id)}">${esc(perceptionState.models[r.model]?.name)} · ${esc(r.id.slice(0,8))}</option>`).join('')}</select></label><button class="secondary" type="submit">Compare measured results</button></form><div id="perception-comparison"></div>`;
  }
  $('#perception-result').innerHTML=html+'</section>';
  $('#perception-image-detail').innerHTML='';
  $('#perception-compare')?.addEventListener('submit',async event=>{
    event.preventDefault();try{
      const comparison=await post('/perception/comparisons',{baseline:id,candidate:$('#perception-other').value});
      $('#perception-comparison').innerHTML=`<div class="table-scroll"><table><thead><tr><th>Metric</th>${comparison.models.map(n=>`<th>${esc(n)}</th>`).join('')}</tr></thead><tbody>${['precision','recall','sku_precision','sku_recall','count_mae','scored_images'].map(k=>`<tr><td>${esc(k.replaceAll('_',' '))}</td>${[comparison.baseline,comparison.candidate].map(r=>`<td>${r.metrics[k]===null?'N/A':Number(r.metrics[k]).toFixed(3)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    }catch(error){notify(error.message,true);}
  });
  if(scroll)$('#perception-result').scrollIntoView({behavior:'smooth'});
}

function inspectPerceptionImage(id) {
  const entry=perceptionState.manifest.images.find(e=>e.id===id);if(!entry)return;
  const prediction=perceptionRun?.result?.predictions.find(p=>p.image_id===id);
  const categories=new Map(perceptionState.manifest.categories.map(c=>[c.id,c.name]));
  $('#perception-image-detail').innerHTML=`<section class="panel detail-panel"><h2>${esc(entry.file_name)}</h2><p class="help">${esc(entry.level)} · ${entry.annotations.length} publisher annotations · ${prediction?prediction.boxes.length+' predictions from selected run':'No predictions selected'}</p><div class="actions"><label><input type="checkbox" id="show-reference" checked> Blue: publisher annotations</label><label><input type="checkbox" id="show-predictions" checked> Orange: model predictions</label></div><div class="rpc-image-wrap"><img id="rpc-detail-image" src="/v1/perception/images/${id}" alt="Original RPC photograph with optional reference and prediction overlays"><canvas id="rpc-boxes" aria-label="Blue reference boxes and orange model predictions"></canvas></div><p class="help">Boxes use original image coordinates. Labels starting R are references; P are predictions. Reference labels are never supplied to validation-image inference.</p><p class="mono">SHA-256 ${esc(entry.sha256)}</p>${prediction?.warnings?.length?`<p class="callout">${prediction.warnings.map(esc).join('; ')}</p>`:''}</section>`;
  const draw=()=>{
    const canvas=$('#rpc-boxes');canvas.width=entry.width;canvas.height=entry.height;
    const context=canvas.getContext('2d');context.font='bold 23px sans-serif';context.lineWidth=5;
    function box(b,label,color){context.strokeStyle=color;context.fillStyle=color;context.strokeRect(...b);const y=Math.max(26,b[1]);context.fillRect(b[0],y-26,context.measureText(label).width+8,28);context.fillStyle='#fff';context.fillText(label,b[0]+4,y-4);}
    if($('#show-reference').checked)entry.annotations.forEach(a=>box(a.bbox,`R ${categories.get(a.category_id)||a.category_id}`,'#125fb7'));
    if($('#show-predictions').checked)prediction?.boxes.forEach((b,i)=>box(b,`P ${prediction.category_ids?categories.get(prediction.category_ids[i])||prediction.category_ids[i]:i+1}`,'#b94708'));
  };
  $('#show-reference').addEventListener('change',draw);$('#show-predictions').addEventListener('change',draw);draw();
  $('#perception-image-detail').scrollIntoView({behavior:'smooth'});
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  try {
    if(button.id==='refresh-perception')await refreshPerception();
    if(button.id==='start-perception'){
      button.disabled=true;
      try{const run=await post('/perception/runs',{model:$('#perception-model').value,idempotency_key:crypto.randomUUID()});await refreshPerception();await inspectPerception(run.id);}finally{button.disabled=false;}
    }
    if(button.dataset.perceptionRun)await inspectPerception(button.dataset.perceptionRun);
    if(button.dataset.perceptionImage)inspectPerceptionImage(Number(button.dataset.perceptionImage));
    if(button.dataset.perceptionCancel){await post('/runs/'+button.dataset.perceptionCancel+'/cancel',{});await refreshPerception();await inspectPerception(button.dataset.perceptionCancel,false);}
  }catch(error){notify(error.message,true);}
});
refreshPerception().catch(error=>notify(error.message,true));
setInterval(async()=>{
  if(document.hidden||!perceptionState.runs.some(r=>!terminal.has(r.status)))return;
  try{await refreshPerception();if(perceptionRun&&!terminal.has(perceptionRun.status))await inspectPerception(perceptionRun.id,false);}catch(error){notify(error.message,true);}
},3000);
