/* Every supplied alert remains inspectable, including unmatched/imported alerts. */
function evidenceTimeline(entry, predictedEvents, matches) {
  const events=entry.inputs.events.map(e=>({t_ms:e.t_ms+entry.inputs.offset_ms,label:`POS · ${e.type}${e.sku?' · '+e.sku:''}`}));
  for(const e of entry.annotation.discrepancies){
    events.push({t_ms:e.start_ms,label:`Reference discrepancy starts · ${e.sku}`});
    events.push({t_ms:e.end_ms,label:`Reference discrepancy ends · ${e.sku}`});
  }
  const matched=new Set(matches.map(m=>m.prediction_id));
  predictedEvents.forEach(e=>events.push({t_ms:e.t_ms,label:`Model alert · ${e.sku} · ${matched.has(e.id)?'matched reference':'unmatched alert'}`}));
  return events.sort((a,b)=>a.t_ms-b.t_ms);
}
if(typeof module!=='undefined')module.exports={evidenceTimeline};
