const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() {this.children=[];this.value='';this.files=[];}
  append(...items) {this.children.push(...items);}
  replaceChildren(...items) {this.children=items;}
  setAttribute() {}
  querySelector() {return new Element();}
  scrollIntoView(options) {this.scrolled=true;this.scrollOptions=options;}
}
const fields=new Map(), elements=new Map();
const field=name=>{if(!fields.has(name))fields.set(name,new Element());return fields.get(name);};
const intake=new Element();intake.elements={namedItem:field};
const get=selector=>{if(!elements.has(selector))elements.set(selector,new Element());return elements.get(selector);};
const document={getElementById:id=>id==='intake' ? intake : get('#'+id),querySelector:selector=>selector==='#intake' ? intake : get(selector),createElement:()=>new Element()};
const payload={preview_only:true,dry_run:false,campaign:{title:'Research preview: Popular long video',
  url:'https://www.youtube.com/watch?v=aaaaaaaaaaa',rules:'Local preview',rights_notes:'Local test'}};
let trends={enabled:true,paused:false,interval_hours:6,provider:'public_search',latest:null};
let libraryError=false;
let library={root:'clips/niches',publishing_enabled:false,ranking_note:'Categories describe topic routing, not predicted views.',categories:[
  {id:'sports',name:'Sports',folder:'clips/niches/sports',clip_count:3,available_clip_count:1,clips:[
    {id:'available-clip',order_id:'saved-order',path:'clips/niches/sports/available.mp4',subtitles:'clips/niches/sports/available.srt',
      caption:'<img src=x onerror=alert(1)> A standalone point.',niche:'sports',routing_basis:'source_metadata',available:true,missing_artifacts:[]},
    {id:'missing-clip',order_id:'saved-order',path:'clips/niches/sports/missing.mp4',subtitles:'clips/niches/sports/missing.srt',
      caption:'Review this second point.',niche:'sports',routing_basis:'source_metadata',available:false,missing_artifacts:['video','subtitles']},
    {id:'changed-clip',order_id:'saved-order',path:'clips/niches/sports/changed.mp4',subtitles:'clips/niches/sports/changed.srt',
      caption:'A changed export.',niche:'sports',routing_basis:'source_metadata',available:false,
      missing_artifacts:[],changed_artifacts:['video'],integrity:'recorded_hashes'}]},
  {id:'business',name:'Business',folder:'clips/niches/business',clip_count:0,available_clip_count:0,clips:[]}]};
let job=null;const requests=[];
const fetch=async(url,options)=>{
  requests.push({url,options});
  if(url==='/examples/practice.srt')return {ok:true,text:async()=>'1\n00:00:00,000 --> 00:00:05,000\nPractice text.\n'};
  let data;
  if(url==='/health') data={kill_switch:false,transcription_installed:true,english_model_ready:true};
  else if(url==='/api/v1/jobs') data={jobs:job ? [job] : []};
  else if(url==='/growth-insights') data={status:'insufficient_data',measured_clip_count:0,minimum_independent_clips:3,
    best_clips:[],worst_clips:[],duration_patterns:[],hook_patterns:[],hashtag_patterns:[],cta_patterns:[],limitations:[]};
  else if(url==='/metrics') data={performance_periods:{daily:[],weekly:[],monthly:[]}};
  else if(url==='/niche-library') {
    if(libraryError)return {ok:false,json:async()=>({detail:'Local files could not be checked.'})};
    data=library;
  }
  else if(url==='/hashtags/suggest') data={action:'review_only',history_status:'insufficient_data',
    suggestion:{hashtags:['#business','#pricing']}};
  else if(url==='/posting-time/instagram') data={basis:'configured_fallback',samples:0,
    recommended_at:'2026-10-22T09:00:00+00:00',timezone:'UTC',followers_per_1000_views:null};
  else if(url==='/api/v1/clipping/trends') data=trends;
  else if(url==='/api/v1/clipping/trends/runs') {
    job={id:'preview-1',payload,output:{},status:'queued',current_step:'source_ingest',created_at:'2026-10-08T10:00:00Z',updated_at:'2026-10-08T10:00:00Z'};
    data=trends.latest={id:'scan-1',status:'completed',auto_preview:true,preview_job_id:job.id,results:[],failures:[],searched_niches:[],updated_at:'2026-10-08T10:00:00Z'};
  }
  else if(url==='/api/v1/clipping/jobs') data=job={id:'campaign-1',payload:JSON.parse(options.body).payload,
    output:{},status:'awaiting_campaign_approval',current_step:'campaign_review',
    created_at:'2026-10-08T10:02:00Z',updated_at:'2026-10-08T10:02:00Z'};
  else throw new Error(`Unexpected request: ${url}`);
  return {ok:true,json:async()=>data};
};
const html=fs.readFileSync('clipping/workspace.html','utf8');
assert(html.includes('id="automatic-start"'), 'Automatic preview control is missing');
assert(html.includes('href="#niche-library"'),'Niche library navigation is missing');
assert(html.includes('id="niche-library"'),'Niche library section is missing');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const window={matchMedia:()=>({matches:true})};
const context={document,window,fetch,setInterval:()=>0,setTimeout,FormData,Date,URL};
vm.runInNewContext(script,context);
vm.runInNewContext(fs.readFileSync('clipping/trends.js','utf8'),context);
async function run() {
  await new Promise(resolve=>setImmediate(resolve));
  assert(requests.some(item=>item.url==='/growth-insights'),'Workspace must load measured growth insights');
  assert.equal(get('#growth-report-status').textContent,
    '0 of 3 required clips have measured follower conversion. Add observations to see patterns.');
  assert(requests.some(item=>item.url==='/metrics'),'Workspace must load measured period aggregates');
  assert.equal(get('#performance-periods').children[1].textContent,'No imported performance observations yet.');
  get('#hashtag-platform').value='instagram';get('#hashtag-niche').value='business';
  get('#hashtag-topic').value='pricing, startup';get('#hashtag-clip-topic').value='Pricing for startups';
  await get('#hashtag-suggest-form').onsubmit({preventDefault(){}});
  const suggestionRequest=requests.find(item=>item.url==='/hashtags/suggest');
  assert.deepEqual(JSON.parse(suggestionRequest.options.body),{platform:'instagram',niche_keywords:['business'],
    topic_keywords:['pricing','startup'],clip_topic:'Pricing for startups'});
  assert.deepEqual(get('#hashtag-suggestions').children.map(item=>item.textContent),['#business','#pricing']);
  get('#posting-time-platform').value='instagram';
  await get('#posting-time-check-button').onclick({currentTarget:get('#posting-time-check-button')});
  assert(requests.some(item=>item.url==='/posting-time/instagram'),'Workspace must request a posting-time basis');
  assert(get('#posting-time-status').textContent.includes('Configured fallback'));
  get('#campaign-nav').onclick();
  assert.equal(get('#manual-intake').open,true,'Campaign navigation must open the form');
  const button=get('#automatic-start');
  assert.equal(typeof button.onclick,'function');
  await button.onclick();
  await new Promise(resolve=>setImmediate(resolve));
  const trendPosts=requests.filter(item=>item.options?.method==='POST' && item.url==='/api/v1/clipping/trends/runs');
  assert.equal(trendPosts.length,1);
  assert.deepEqual(JSON.parse(trendPosts[0].options.body),{auto_preview:true});
  assert.equal(button.disabled,false);
  assert.equal(field('title').value,'');
  assert.equal(field('source_url').value,'');
  const text=element=>[element.textContent || '',...element.children.map(item=>typeof item==='string' ? item : text(item))].join(' ');
  assert(requests.some(item=>item.url==='/niche-library'),'Workspace must load the local niche library');
  assert(text(get('#niche-library-status')).includes('3 saved clips'));
  assert(text(get('#niche-library-status')).includes('1 available'));
  assert(text(get('#niche-library-content')).includes('clips/niches/sports'));
  assert(text(get('#niche-library-content')).includes('available.mp4'));
  assert(text(get('#niche-library-content')).includes('Files missing: video, subtitles'));
  assert(text(get('#niche-library-content')).includes('Files changed: video'));
  assert(text(get('#niche-library-content')).includes('<img src=x onerror=alert(1)> A standalone point.'),
    'Imported captions must remain literal text');
  get('#niche-library-filter').value='business';get('#niche-library-filter').onchange();
  assert(text(get('#niche-library-content')).includes('No clips in Business yet.'));
  assert(!text(get('#niche-library-content')).includes('available.mp4'));
  libraryError=true;await get('#niche-library-refresh').onclick();
  assert(text(get('#niche-library-status')).includes('Local files could not be checked.'));
  assert.equal(get('#niche-library-refresh').disabled,false,'Failed refresh must remain retryable');
  assert.equal(get('#niche-library-filter').value,'business','Refresh errors must preserve the filter');
  libraryError=false;library={...library,categories:[]};await get('#niche-library-refresh').onclick();
  assert(text(get('#niche-library-content')).includes('No saved clips yet.'));
  assert.equal(requests.filter(item=>item.url==='/niche-library' && item.options?.method==='POST').length,0,
    'Browsing the local library must not post or publish');
  assert(text(get('#detail')).includes('Popular long video'));
  const firstRunButton=get('#jobs').children[0];
  firstRunButton.onclick();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(get('#jobs').children[0],firstRunButton,'Unchanged polling must preserve the recent-run control');
  assert(text(get('#map-preview')).includes('Not ready'));
  job={...job,status:'failed',updated_at:'2026-10-08T10:00:30Z',error:'Source unavailable'};
  get('#jobs').children[0].onclick();
  await new Promise(resolve=>setImmediate(resolve));
  assert(text(get('#map-source')).includes('Failed'));
  assert(text(get('#detail')).includes('No preview was created.'));
  assert(text(get('#detail')).includes('View error details'));
  assert(text(get('#map-transcript')).includes('Waiting'));
  assert(text(get('#map-preview')).includes('Not ready'));
  job={...job,status:'completed',current_step:'preview_complete',updated_at:'2026-10-08T10:01:00Z',
    output:{preview_only:true,source_path:'source.mp4',transcript_path:'transcript.json',
      caption:'Why does this fail?',transcript_origin:'faster_whisper:en',
      selected_clip_plan:{start_seconds:10,duration_seconds:30},clip_path:'clip.mp4',quality:{checks:{video:true}}}};
  vm.runInNewContext('0',{});
  const jobButton=get('#jobs').children[0];
  jobButton.onclick();
  await new Promise(resolve=>setImmediate(resolve));
  assert(text(get('#detail')).includes('preview complete'));
  assert(text(get('#detail')).includes('Post caption'));
  assert(text(get('#detail')).includes('Why does this fail?'));
  assert(text(get('#detail')).includes('faster_whisper:en'));
  assert(!text(get('#detail')).includes('Approve this clip'));
  assert(text(get('#map-source')).includes('Available'));
  assert(text(get('#map-transcript')).includes('Available'));
  assert(text(get('#map-plan')).includes('10s'));
  assert(text(get('#map-preview')).includes('Ready'));
  field('dry_run').checked=true;
  let modelDuration;
  window.clipStudio={refresh(){modelDuration=field('duration').value;}};
  await get('#sample-srt').onclick();
  assert.equal(modelDuration,'5','Loading sample subtitles must refresh the desired length in the model');
  for(const [name,value] of Object.entries({title:'Campaign test',campaign_url:'https://example.com/campaign',
    platform:'tiktok',experience:'current',rules:'Keep context',rights_notes:'Fixture permission',
    duration:30,start:0,aspect:'9:16'}))field(name).value=value;
  field('dry_run').checked=true;
  window.clipForm={validate:()=>false};
  await intake.onsubmit({preventDefault(){}});
  assert.equal(requests.filter(item=>item.url==='/api/v1/clipping/jobs').length,0,'Invalid guided forms must not create jobs');
  window.clipForm.validate=()=>true;
  await intake.onsubmit({preventDefault(){}});
  assert.equal(get('#workspace').scrolled,true,'Campaign submission must return to the preview');
  assert.equal(get('#workspace').scrollOptions.behavior,'auto','Reduced motion must suppress smooth scrolling');
  assert(text(get('#detail')).includes('Campaign test'));
  console.log('Long-video search starts without form choices, hands off one job, and shows subtitles and the post caption.');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
