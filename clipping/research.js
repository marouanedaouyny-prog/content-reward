/* Local research controls. Imported text is always rendered with textContent. */
(() => {
  const intake = document.querySelector('#intake');
  const field = name => intake.elements.namedItem(name);
  const el = (tag, text) => {const item=document.createElement(tag);if(text!==undefined)item.textContent=text;return item;};
  const notice = document.querySelector('#research-message');
  const endpoint = '/api/v1/clipping/research';
  const scrollBehavior=()=>window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ? 'auto' : 'smooth';
  function message(text, error=false) {
    notice.textContent=text;notice.className=error ? 'error' : 'muted';
    notice.setAttribute('role',error ? 'alert' : 'status');
  }
  function openResearch() {
    document.getElementById('manual-intake').open=true;
    window.clipForm?.show('clip');
    document.getElementById('research-tools').open=true;
    const sample=document.getElementById('metadata-file');
    sample.scrollIntoView({behavior:scrollBehavior(),block:'center'});sample.focus({preventScroll:true});
  }
  document.getElementById('open-research').onclick=openResearch;

  async function request(path, body) {
    const multipart = body instanceof FormData;
    const options = body ? {method:'POST',body:multipart ? body : JSON.stringify(body),
      headers:multipart ? {} : {'Content-Type':'application/json'}} : {};
    const response=await fetch(endpoint+path,options),result=await response.json();
    if(!response.ok) {
      const detail=Array.isArray(result.detail) ? result.detail.map(item=>item.msg).join('; ') : result.detail;
      throw new Error(detail || 'Research request failed');
    }
    return result;
  }

  function bind(id, action) {
    const button=document.getElementById(id);
    button.onclick=async()=>{button.disabled=true;message('');try{await action();}
      catch(error){message(error.message,true);if(id==='source-check')document.getElementById('source-details').textContent=error.message;}
      finally{button.disabled=false;}};
  }

  window.renderClipIdeas = (container, ideas, payload) => {
    ideas.forEach((idea,index)=>{
      const card=el('div');card.className='idea';const plan=idea.clip_plan;
      card.append(el('strong',`Option ${index+1}: ${plan.start_seconds}s start / ${plan.duration_seconds}s long`),
        el('p',idea.source_excerpt),el('p',idea.reasons.join(' · ')),
        el('small',`Editorial score ${idea.editorial_score}. ${idea.note}`));
      const button=el('button','Use this cut in a new review task');button.type='button';button.className='secondary';
      button.onclick=()=>{
        if(payload) {
          const campaign=payload.campaign;
          for(const [name,value] of Object.entries({title:campaign.title,campaign_url:campaign.url,
            platform:campaign.platform,experience:campaign.experience || 'current',rules:campaign.rules,
            rights_notes:campaign.rights_notes,duration_min:campaign.duration_min ?? '',
            duration_max:campaign.duration_max ?? '',rate:campaign.rate_per_1000 ?? '',
            source_url:payload.source_url || '',saved_source_path:payload.source_path || '',
            language:payload.language || '',caption:payload.caption || '',
            transcript_srt:payload.transcript_srt || '',research_keywords:payload.research_keywords || ''}))field(name).value=value;
          field('pre_post_review').checked=!!campaign.pre_post_review;
          field('dry_run').checked=!!payload.dry_run;field('video').value='';
          document.getElementById('source-details').textContent=`Source carried over from ${campaign.title}. Review the source and campaign before creating the new task.`;
        }
        field('start').value=plan.start_seconds;field('duration').value=plan.duration_seconds;
        field('aspect').value=plan.aspect_ratio;
        field('auto_clip').checked=false;
        document.getElementById('manual-intake').open=true;
        window.clipForm?.show('clip');
        if(!field('caption').value.trim())field('caption').value=idea.caption;
        window.clipStudio?.refresh();
        message('Cut selected. Check source, campaign limits, caption and disclosure, then create a new review task.');
        field('start').scrollIntoView({behavior:scrollBehavior(),block:'center'});
      };
      card.append(button);container.append(card);
    });
  };
  for(const name of ['source_url','video'])field(name).addEventListener('change',()=>{field('saved_source_path').value='';});

  function applyBrief(brief) {
    try {
      const language=field('language').value;
      if(language && language!==brief.language)throw new Error('This brief uses a different language. Import a sample matching the source language before applying it.');
      const enteredMinimum=field('duration_min').value ? Number(field('duration_min').value) : 0;
      const minimum=Math.max(1,enteredMinimum);
      const maximum=field('duration_max').value ? Math.min(180,Number(field('duration_max').value)) : 180;
      if(!Number.isFinite(minimum) || !Number.isFinite(maximum) || enteredMinimum<0 || minimum>maximum || maximum<1)throw new Error('Correct the campaign minimum and maximum clip lengths before using this brief.');
      const target=Math.max(minimum,Math.min(maximum,brief.target_duration));
      field('duration').value=target;field('research_keywords').value=brief.keywords.join(', ');
      field('auto_clip').checked=true;document.getElementById('manual-intake').open=true;
      window.clipForm?.show('clip');window.clipStudio?.refresh();
      message(`Brief applied to this campaign: ${target}s desired length. ${target!==brief.target_duration ? 'Length adjusted to the campaign limits. ' : ''}The source transcript will select the moment. Review the campaign and create the task when ready.`);
      field('duration').scrollIntoView({behavior:scrollBehavior(),block:'center'});field('duration').focus({preventScroll:true});
    } catch(error) {message(error.message,true);}
  }

  function renderReport(report) {
    const root=document.getElementById('metadata-report');root.replaceChildren();
    const synthetic=report.source==='synthetic_demo',brief=report.planning_brief;
    document.getElementById('research-map-status').textContent=synthetic ? 'Synthetic demonstration only. No real dataset sample is loaded.' : `${report.matched_records} matching posts in an imported sample. ${brief ? `Brief ready: ${brief.topic}, ${brief.target_duration}s.` : 'More suitable evidence is needed for a brief.'}`;
    root.append(el('strong',report.source==='synthetic_demo' ? 'Synthetic demo — no real TikTok findings' : 'Operator-supplied research sample'),
      el('p',`${report.valid_records} valid records; ${report.matched_records} match; ${report.invalid_records} invalid; ${report.duplicate_records} duplicates; ${report.empty_captions} empty captions.`));
    if(brief) {
      const summary=el('div');summary.className='research-brief';
      summary.append(el('h3',synthetic ? 'Example planning brief' : 'Suggested planning brief'),
        el('p',`${brief.topic} · ${brief.target_duration}s desired length · ${brief.support_count} supporting posts`),
        el('p',`${brief.month} / ${brief.language} / ${brief.country}. ${brief.reason}`),
        el('p',report.brief_note),el('small',brief.note));
      if(!synthetic && brief.can_apply) {
        const use=el('button','Use brief for this campaign');use.type='button';use.className='secondary';
        use.onclick=()=>applyBrief(brief);summary.append(use,
          el('small','Fills topic keywords and desired length, then enables transcript planning. The automatic IShowSpeed preview uses its saved settings.'));
      } else summary.append(el('p','Demo briefs explain the controls and cannot be applied to a campaign.'));
      root.append(summary);
    } else root.append(el('p',report.brief_note));
    if(!report.cohorts.length)root.append(el('p','No group has at least 10 matching posts. Add a broader sample or adjust filters.'));
    else {
      const wrap=el('div');wrap.className='table-wrap';const table=el('table'),head=el('thead'),row=el('tr');
      for(const title of ['Topic','Month / labels','Length','Posts','Median views','Share / view','Save / view']) {const cell=el('th',title);cell.scope='col';row.append(cell);}head.append(row);table.append(head);
      const body=el('tbody'),rate=value=>value===null ? '—' : `${(value*100).toFixed(2)}%`;
      report.cohorts.slice(0,30).forEach(item=>{const tr=el('tr');for(const value of [item.topic,`${item.month} / ${item.language} / ${item.country}`,`${item.duration_min}–${item.duration_max}s`,item.count,item.median_views,`${rate(item.median_share_rate)} (${item.share_observations} measured)`,`${rate(item.median_save_rate)} (${item.save_observations} measured)`])tr.append(el('td',String(value)));body.append(tr);});
      table.append(body);wrap.append(table);root.append(wrap);
    }
    root.append(el('p',report.note));
    const details=el('details');details.append(el('summary','How to interpret these results'));
    report.limitations.forEach(text=>details.append(el('p',text)));root.append(details);
    const download=el('button','Download research report');download.type='button';download.className='secondary';
    download.onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const link=el('a');link.href=url;link.download='clip-research-report.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};root.append(download);
  }

  bind('source-check',async()=>{
    const result=await request('/sources',{url:field('source_url').value.trim()});
    field('source_url').value=result.url;
    document.getElementById('source-details').textContent=`${result.title} — ${result.creator}, ${Math.round(result.duration)} seconds. ${result.note}`;
  });
  bind('metadata-demo',async()=>renderReport(await request('/demo')));
  bind('metadata-analyze',async()=>{
    const file=document.getElementById('metadata-file').files[0];if(!file)throw new Error('Choose a local CSV or JSONL metadata sample.');
    if(file.size>25*1024*1024)throw new Error('Choose a sample smaller than 25 MB.');
    const body=new FormData();body.append('file',file);body.append('keywords',field('research_keywords').value);
    body.append('language',document.getElementById('research-language').value.trim());body.append('country',document.getElementById('research-country').value.trim());
    renderReport(await request('/reports',body));
  });
  bind('suggest-cuts',async()=>{
    const srt=field('transcript_srt').value.trim();if(!srt)throw new Error('Import or paste the matching source SRT first, or enable automatic planning after approval.');
    const desired=Number(field('duration').value);
    const ideas=await request('/plans',{transcript_srt:srt,target_duration:desired,
      min_duration:field('duration_min').value ? Number(field('duration_min').value) : Math.min(15,desired),
      max_duration:field('duration_max').value ? Number(field('duration_max').value) : Math.max(60,desired),
      keywords:field('research_keywords').value});
    const root=document.getElementById('clip-ideas');root.replaceChildren();window.renderClipIdeas(root,ideas);
  });
})();
