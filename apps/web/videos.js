let videoData = null, videoAnalysis = null;
async function refreshVideos() {
  videoData=await api('/videos');
  if(!videoData.available){$('#video-library').innerHTML=empty('No original videos installed','Acquire the publisher subset with python -m checkoutcheck.retail_video.');return;}
  const m=videoData.manifest;
  $('#video-library').innerHTML=`<div class="callout">Real shelf-interaction recordings from <a href="${esc(m.source)}" target="_blank" rel="noreferrer">Standard Cognition · RetailAction</a>. The publisher anonymized faces and selected informative frames. These are not continuous checkout transactions and contain no POS/payment logs.</div><p class="help">Licensed under the <a href="${esc(m.source)}/blob/${esc(m.revision)}/LICENSE" target="_blank" rel="noreferrer">Standard.AI Dataset License</a>. Copyright © Standard Corp. All Rights Reserved. Local research subset · ${m.videos.length} original clips · ${esc(m.source_split)} split.</p><div class="panel table-scroll"><table><thead><tr><th>Original recording</th><th>Source bytes</th><th>Diagnostics</th><th></th></tr></thead><tbody>${videoData.videos.map(v=>`<tr><td>${esc(v.id)}</td><td>${(v.bytes/1024).toFixed(0)} KB</td><td>${v.analyzed?'Available':'Not run'}</td><td><button class="row-link" data-video-open="${esc(v.id)}">Inspect video →</button></td></tr>`).join('')}</tbody></table></div>`;
}
async function inspectVideo(id) {
  const entry=videoData.videos.find(v=>v.id===id);if(!entry)return;
  videoAnalysis=null;
  $('#video-inspector').innerHTML=`<section class="panel detail-panel"><div class="detail-actions"><h2>${esc(id)}</h2><button class="secondary" id="analyze-video" data-id="${esc(id)}">Run OpenCV diagnostics</button></div><div class="video-wrap"><video id="source-video" src="/v1/videos/${esc(id)}/media" controls preload="metadata" aria-label="Original publisher retail video"></video><canvas id="source-video-overlay" aria-label="Publisher action annotation"></canvas></div><div id="source-video-error" class="error" hidden></div><div id="video-analysis-content"></div><p class="mono">Original SHA-256 ${esc(entry.sha256)}</p></section>`;
  const video=$('#source-video');
  video.addEventListener('timeupdate',drawVideoAnnotation);
  video.addEventListener('seeked',drawVideoAnnotation);
  video.addEventListener('loadedmetadata',drawVideoAnnotation);
  video.addEventListener('error',()=>{const error=$('#source-video-error');error.hidden=false;error.textContent='The browser could not play this original codec. The source has been retained unchanged.';});
  $('#analyze-video').addEventListener('click',async event=>{
    const button=event.currentTarget;button.disabled=true;button.textContent='Analyzing original frames…';
    try{videoAnalysis=await post('/videos/'+id+'/analyze',{});renderVideoAnalysis(id);await refreshVideos();}catch(error){notify(error.message,true);}finally{button.disabled=false;button.textContent='Run OpenCV diagnostics';}
  });
  if(entry.analyzed){videoAnalysis=await api('/videos/'+id+'/analysis');renderVideoAnalysis(id);}
  $('#video-inspector').scrollIntoView({behavior:'smooth'});
}
function renderVideoAnalysis(id) {
  const a=videoAnalysis;
  $('#video-analysis-content').innerHTML=`<div class="stat-grid">${stat('Decoded frames',a.frames.length,'All original encoded frames')}${stat('Playback duration',a.playback_duration_seconds.toFixed(2)+' s','Encoded video time')}${stat('Source duration',a.source_duration_seconds.toFixed(2)+' s','Publisher original timeline')}${stat('OpenCV version',a.opencv_version,'Frame differences and sharpness')}</div><div class="callout">Playback time and source time differ because the publisher selected frames. The table preserves their exact mapping. Blue annotations are publisher labels, not model predictions. Motion diagnostics do not establish a take, scan, payment or discrepancy.</div><label><input type="checkbox" id="show-video-annotation" checked> Show publisher interaction point</label><p id="source-time-display" class="help"></p><h3>Publisher action annotations</h3><div class="actions">${a.publisher_annotations.map((label,i)=>`<button class="secondary" data-source-action="${i}">${esc(label.label)} · source ${label.source_start_seconds.toFixed(2)}–${label.source_end_seconds.toFixed(2)} s</button>`).join('')||'<p class="help">No publisher action annotation is present for this clip.</p>'}</div><h3>Frame evidence</h3><div class="table-scroll video-frame-table"><table><thead><tr><th>Frame</th><th>Playback time</th><th>Source time</th><th>Changed pixels</th><th>Sharpness</th></tr></thead><tbody>${a.frames.map(f=>`<tr><td><button class="row-link" data-video-frame="${f.index}">${f.index+1} →</button></td><td>${f.playback_seconds.toFixed(3)} s</td><td>${f.source_seconds.toFixed(3)} s</td><td>${f.changed_pixel_fraction===null?'N/A':(100*f.changed_pixel_fraction).toFixed(1)+'%'}</td><td>${f.laplacian_variance.toFixed(1)}</td></tr>`).join('')}</tbody></table></div><a href="/v1/videos/${esc(id)}/export">Export video diagnostics ↓</a><p class="help">${a.limitations.map(esc).join(' ')}</p>`;
  $('#show-video-annotation').addEventListener('change',drawVideoAnnotation);
  drawVideoAnnotation();
}
function drawVideoAnnotation() {
  const video=$('#source-video'),canvas=$('#source-video-overlay'),a=videoAnalysis;
  if(!video||!canvas)return;
  canvas.width=video.videoWidth||600;canvas.height=video.videoHeight||600;
  const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
  if(!a)return;
  const frame=a.frames[Math.min(a.frames.length-1,Math.floor(video.currentTime*a.fps+0.001))];
  $('#source-time-display').textContent=`Frame ${frame.index+1} · playback ${video.currentTime.toFixed(3)} s · original source ${frame.source_seconds.toFixed(3)} s`;
  if(!$('#show-video-annotation').checked)return;
  for(const label of a.publisher_annotations){
    if(frame.source_seconds<label.source_start_seconds||frame.source_seconds>label.source_end_seconds)continue;
    const x=label.position.x*canvas.width,y=label.position.y*canvas.height;
    ctx.strokeStyle='#125fb7';ctx.lineWidth=4;ctx.beginPath();ctx.arc(x,y,16,0,Math.PI*2);ctx.stroke();ctx.font='bold 16px sans-serif';ctx.fillStyle='#125fb7';ctx.fillText('Publisher: '+label.label,Math.max(5,Math.min(x+20,canvas.width-180)),Math.max(20,y));
  }
}
document.addEventListener('click',async event=>{
  const b=event.target.closest('button');if(!b)return;
  try{
    if(b.dataset.videoOpen)await inspectVideo(b.dataset.videoOpen);
    if(b.dataset.videoFrame!==undefined){const f=videoAnalysis.frames[Number(b.dataset.videoFrame)];$('#source-video').currentTime=f.playback_seconds;}
    if(b.dataset.sourceAction!==undefined){const a=videoAnalysis.publisher_annotations[Number(b.dataset.sourceAction)];const f=videoAnalysis.frames.find(f=>f.source_seconds>=a.source_start_seconds);if(f)$('#source-video').currentTime=f.playback_seconds;}
  }catch(error){notify(error.message,true);}
});
refreshVideos().catch(error=>notify(error.message,true));
