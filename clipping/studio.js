/* Local layout model and progressive campaign setup. No media or network side effects. */
(() => {
  const byId=id=>document.getElementById(id);
  const form=byId('intake'),field=name=>form.elements.namedItem(name);
  const panes=[...document.querySelectorAll('[data-form-pane]')];
  const steps=[...document.querySelectorAll('[data-form-step]')];
  const order=['campaign','source','clip'],titles=['Campaign brief','Source video','Clip settings'];
  let current=0;
  const error=byId('form-error');

  function show(name) {
    const index=order.indexOf(name);if(index<0)return;
    current=index;
    panes.forEach(pane=>{pane.hidden=pane.dataset.formPane!==name;});
    steps.forEach(step=>{
      if(step.dataset.formStep===name)step.setAttribute('aria-current','step');
      else step.removeAttribute('aria-current');
    });
    byId('form-back').hidden=index===0;
    byId('form-next').hidden=index===2;
    byId('review-submit').hidden=index!==2;
    byId('form-next').textContent=index===0 ? 'Next: source video' : 'Next: clip settings';
    byId('form-progress').textContent=`Step ${index+1} of 3 · ${titles[index]}`;
    updateReview();
  }

  function fail(name,text,control) {
    byId('manual-intake').open=true;show(name);error.textContent=text;
    if(control?.checkValidity()===false)control.reportValidity();
    control?.focus();return false;
  }

  function validatePane(name) {
    error.textContent='';
    const pane=panes.find(item=>item.dataset.formPane===name);
    for(const control of pane.querySelectorAll('input,select,textarea')) {
      if(!control.checkValidity())return fail(name,control.validationMessage || 'Complete the required fields.',control);
      if(control.required && typeof control.value==='string' && !control.value.trim())
        return fail(name,'Enter a value for the required field.',control);
    }
    if(name==='campaign') {
      const minimum=field('duration_min').value,maximum=field('duration_max').value;
      if(minimum && maximum && Number(minimum)>Number(maximum))
        return fail(name,'The campaign minimum must be no longer than its maximum.',field('duration_max'));
    }
    if(name==='source' && !field('dry_run').checked) {
      const sources=Number(!!field('source_url').value.trim())+Number(!!field('video').files.length)+Number(!!field('saved_source_path').value);
      if(sources!==1)return fail(name,'Upload one authorized video or provide its source URL.',field('source_url'));
    }
    if(name==='clip') {
      const duration=Number(field('duration').value),minimum=Number(field('duration_min').value || 0);
      const maximum=Number(field('duration_max').value || 180);
      if(duration<minimum || duration>maximum)return fail(name,'Set a clip length within the campaign minimum and maximum.',field('duration'));
    }
    return true;
  }

  function validate() {
    for(const name of order)if(!validatePane(name))return false;
    return true;
  }
  function go(index) {
    if(index>current)for(let position=0;position<index;position++)if(!validatePane(order[position]))return;
    error.textContent='';show(order[index]);
  }
  steps.forEach(button=>{button.onclick=()=>go(order.indexOf(button.dataset.formStep));});
  byId('form-next').onclick=()=>go(Math.min(2,current+1));
  byId('form-back').onclick=()=>go(Math.max(0,current-1));
  form.setAttribute('data-guided','true');
  form.addEventListener('reset',()=>{error.textContent='';show('campaign');});
  window.clipForm={show,validate};

  const formats={
    '9:16':{label:'Vertical',size:'1080 × 1920',width:'180px',ratio:'9 / 16'},
    '1:1':{label:'Square',size:'1080 × 1080',width:'230px',ratio:'1 / 1'},
    '16:9':{label:'Landscape',size:'1920 × 1080',width:'320px',ratio:'16 / 9'},
  };
  const buttons=[...document.querySelectorAll('[data-studio-format]')];
  const model=byId('studio-model'),angle=byId('studio-angle');
  const motion=window.matchMedia?.('(prefers-reduced-motion: reduce)');
  let aspect=formats[field('aspect').value] ? field('aspect').value : '9:16';

  function updateReview() {
    const platform={youtube:'YouTube Shorts',instagram:'Instagram Reels',tiktok:'TikTok'}[field('platform').value] || 'Selected platform';
    byId('draft-summary').textContent=`${field('dry_run').checked ? 'Practice task' : 'Campaign task'} · ${platform} · ${field('duration').value || '—'}s desired length · ${field('aspect').value || '9:16'}. The finished clip still needs review.`;
  }
  function updateAngle() {
    const value=Number(angle.value),rotation=motion?.matches ? 0 : Number.isFinite(value) ? Math.max(-30,Math.min(30,value)) : 0;
    model.style.setProperty('--view-angle',`${rotation}deg`);
    angle.disabled=!!motion?.matches;
    byId('studio-angle-value').textContent=`${rotation}°`;
    byId('studio-motion-note').textContent=motion?.matches ? 'Reduced motion: the layout is shown flat.' : 'Change the angle to inspect the video and caption layers.';
  }
  function refresh() {
    const format=formats[aspect];
    model.dataset.format=aspect;
    model.style.setProperty('--model-width',format.width);model.style.setProperty('--frame-ratio',format.ratio);
    byId('studio-format-label').textContent=`${format.label} · ${aspect} · ${format.size}`;
    byId('studio-caption').textContent=field('caption').value.trim() || 'Caption placement';
    const duration=Number(field('duration').value);
    byId('studio-duration').textContent=Number.isFinite(duration) && duration>=1 && duration<=180 ? `${duration}s desired length` : 'Set a clip length in the form';
    buttons.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.studioFormat===aspect)));
    updateAngle();updateReview();
  }
  buttons.forEach(button=>{button.onclick=()=>{aspect=button.dataset.studioFormat;refresh();};});
  angle.oninput=updateAngle;
  byId('studio-front').onclick=()=>{angle.value='0';updateAngle();};
  byId('studio-use-format').onclick=()=>{
    field('aspect').value=aspect;byId('manual-intake').open=true;show('clip');
    byId('studio-apply-note').textContent=`${formats[aspect].label} format applied to the campaign form. Your source, caption and permissions are preserved.`;
    field('aspect').focus();refresh();
  };
  form.addEventListener('input',refresh);
  field('aspect').addEventListener('change',()=>{if(formats[field('aspect').value])aspect=field('aspect').value;refresh();});
  motion?.addEventListener?.('change',updateAngle);
  window.clipStudio={refresh};
  show('campaign');refresh();
})();
