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
let job=null;const requests=[];
const fetch=async(url,options)=>{
  requests.push({url,options});
  if(url==='/examples/practice.srt')return {ok:true,text:async()=>'1\n00:00:00,000 --> 00:00:05,000\nPractice text.\n'};
  let data;
  if(url==='/health') data={kill_switch:false,transcription_installed:true,english_model_ready:true};
  else if(url==='/api/v1/jobs') data={jobs:job ? [job] : []};
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
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const window={matchMedia:()=>({matches:true})};
const context={document,window,fetch,setInterval:()=>0,setTimeout,FormData,Date,URL};
vm.runInNewContext(script,context);
vm.runInNewContext(fs.readFileSync('clipping/trends.js','utf8'),context);
async function run() {
  await new Promise(resolve=>setImmediate(resolve));
  get('#campaign-nav').onclick();
  assert.equal(get('#manual-intake').open,true,'Campaign navigation must open the form');
  const button=get('#automatic-start');
  assert.equal(typeof button.onclick,'function');
  await button.onclick();
  await new Promise(resolve=>setImmediate(resolve));
  const posted=requests.filter(item=>item.options?.method==='POST');
  assert.equal(posted.length,1);
  assert.equal(posted[0].url,'/api/v1/clipping/trends/runs');
  assert.deepEqual(JSON.parse(posted[0].options.body),{auto_preview:true});
  assert.equal(button.disabled,false);
  assert.equal(field('title').value,'');
  assert.equal(field('source_url').value,'');
  const text=element=>[element.textContent || '',...element.children.map(item=>typeof item==='string' ? item : text(item))].join(' ');
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
