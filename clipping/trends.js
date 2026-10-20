/* Saved research evidence and private-preview handoff. */
(() => {
  const byId=id=>document.getElementById(id),base='/api/v1/clipping/trends';
  const form=byId('intake'),field=name=>form.elements.namedItem(name);
  let current,refreshing=false,fingerprint='',handedOff='';
  const node=(tag,text,className)=>{const element=document.createElement(tag);if(text!==undefined)element.textContent=text;if(className)element.className=className;return element;};
  const date=value=>value ? new Date(value).toLocaleString() : 'Not recorded';
  const number=value=>value===null || value===undefined ? 'Unknown' : Number(value).toLocaleString(undefined,{maximumFractionDigits:1});
  async function api(path='',data) {
    const response=await fetch(base+path,data===undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result=await response.json();if(!response.ok)throw new Error(result.detail || 'Research request failed');return result;
  }
  function problem(error) {byId('trends-errors').replaceChildren(node('p',error.message,'error'));}
  function button(root,title,callback) {
    const control=node('button',title);control.type='button';control.className='secondary';
    control.onclick=async()=>{control.disabled=true;try {await callback();}catch(error){problem(error);}finally{control.disabled=false;}};
    root.append(control);return control;
  }
  async function preview(id) {
    const job=await api(`/runs/${current.latest.id}/preview`,id ? {candidate_id:id} : {});
    byId('trends-status').textContent='Private preview queued. Follow its progress in Preview.';
    await window.selectClippingJob?.(job.id);
  }
  function useSource(item) {
    field('video').value='';field('saved_source_path').value='';field('source_url').value=item.url;
    field('dry_run').checked=false;field('research_keywords').value=item.niches.join(', ').slice(0,200);
    if(!field('caption').value.trim())field('caption').value=item.title;
    byId('manual-intake').open=true;window.clipForm?.show('source');window.clipStudio?.refresh();
    byId('trends-status').textContent='Source copied. Check its permission in the campaign brief before creating a task.';
    field('source_url').scrollIntoView({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',block:'center'});
    field('source_url').focus({preventScroll:true});
  }
  function render(state) {
    current=state;const run=state.latest;
    if(run?.preview_job_id && run.preview_job_id!==handedOff) {
      handedOff=run.preview_job_id;window.selectClippingJob?.(handedOff);
      if(byId('automatic-message'))byId('automatic-message').textContent='One source selected. Follow its download, speech transcription, highlight selection and captions in Preview.';
    }
    if(run?.auto_preview && !run.preview_job_id && byId('automatic-message')) {
      byId('automatic-message').textContent=run.preview_error || (run.status==='retry_scheduled' ?
        'YouTube search connection unavailable. No clip has been generated; the saved search will retry.' :
        run.status==='failed' ? 'YouTube search failed. See the errors in YouTube long-video search.' : 'Searching for popular long videos across six niches…');
    }
    byId('trends-toggle').textContent=state.enabled ? 'Pause research agent' : 'Resume research agent';
    byId('trends-provider').textContent=state.provider==='selenium_browser' ? 'Chrome browser search · Selenium' : state.provider==='youtube_api' ? 'YouTube API · recent niche searches' : 'Public YouTube search · optional API connection available';
    byId('trends-next').textContent=state.paused ? 'Workspace processing is paused.' : !state.enabled ? 'Automatic research is paused.' :
      run?.status==='retry_scheduled' ? `Connection retry: ${date(run.next_attempt_at)}.` :
      state.next_scan_at ? `Next scan: ${date(state.next_scan_at)}. The agent refreshes every ${state.interval_hours} hours while the app runs.` : 'The agent will start its first scan automatically.';
    byId('trends-status').textContent=!run ? 'No saved research yet.' : run.status==='running' ? `Searching niches… ${(run.searched_niches || []).length} of 6 checked.` :
      run.status==='queued' ? 'Research queued. Your video workflow continues separately.' :
      run.status==='retry_scheduled' ? 'Research connection unavailable. Saved findings are retained for the next retry.' :
      run.status==='failed' ? 'The scan could not finish. Check the search errors below.' :
      run.status==='partial' ? 'Some searches finished. Remaining search errors are shown below.' : `Scan saved: ${date(run.updated_at)}.`;
    byId('trends-best').disabled=state.paused || !(run?.results || []).some(item=>item.eligible_preview);
    byId('trends-run').disabled=state.paused || ['queued','running','retry_scheduled'].includes(run?.status);
    const key=JSON.stringify([run?.id,run?.updated_at,run?.status,run?.results,run?.failures]);
    if(key===fingerprint)return;fingerprint=key;
    const results=byId('trends-results');results.replaceChildren();
    results.textContent=run?.results?.length ? '' : 'No verified source results yet. Research will show real findings after a successful search.';
    byId('trends-summary').textContent=run ? `${run.results.length} distinct sources · ${(run.searched_niches || []).length} niches searched. ${run.ranking_note}` : 'Gaming, AI & technology, business, fitness, sport, culture & comedy. No niche choice required.';
    for(const item of (run?.results || []).slice(0,12)) {
      const row=node('article',undefined,'trend-row'),heading=node('h3'),link=node('a',item.title);
      link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';heading.append(link);row.append(heading);
      row.append(node('p',`${item.creator} · ${item.niches.join(', ')}`,'muted'));
      row.append(node('p',`${number(item.views)} views · ${number(item.duration==null ? null : item.duration/60)} minutes · Published ${date(item.published_at)} · Observed ${date(item.observed_at)}`,'trend-facts'));
      row.append(node('p',item.measured_growth_per_hour!==null ? `${number(item.measured_growth_per_hour)} views/hour between saved observations.` :
        `${number(item.views_per_hour_since_upload)} views/hour since upload (lifetime average; recent growth unmeasured).`,'trend-signal'));
      const actions=node('div',undefined,'buttons');button(actions,'Use source in campaign',()=>useSource(item));
      if(item.eligible_preview)button(actions,'Prepare private preview',()=>preview(item.id));
      else row.append(node('p','A preview needs a recorded source over 20 minutes and up to two hours, with a verified recent date and view count.','muted'));
      row.append(actions);results.append(row);
    }
    const errors=byId('trends-errors');errors.replaceChildren();
    for(const failure of run?.failures || [])errors.append(node('p',`${failure.niche}: ${failure.message}`,'error'));
  }
  async function refresh() {
    if(refreshing)return;refreshing=true;
    try {render(await api());}catch(error){byId('trends-status').textContent='Research status unavailable. Saved scans remain in the workspace.';problem(error);}finally{refreshing=false;}
  }
  byId('trends-run').onclick=async()=>{byId('trends-run').disabled=true;try {await api('/runs',{});await refresh();}catch(error){problem(error);}finally{byId('trends-run').disabled=!!current?.paused || ['queued','running','retry_scheduled'].includes(current?.latest?.status);}};
  byId('trends-toggle').onclick=async()=>{try {render(await api('/schedule',{enabled:!current?.enabled}));}catch(error){problem(error);}};
  byId('trends-best').onclick=async()=>{byId('trends-best').disabled=true;try {await preview();}catch(error){problem(error);}finally{byId('trends-best').disabled=!!current?.paused || !(current?.latest?.results || []).some(item=>item.eligible_preview);}};
  async function startPreview() {
    const run=await api('/runs',{auto_preview:true});await refresh();return run;
  }
  window.trendResearch={refresh,startPreview};refresh();setInterval(refresh,5000);
})();
