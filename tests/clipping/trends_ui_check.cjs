const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
class Element {
  constructor(){this.children=[];this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.checked=false;this.files=[];}
  append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}
  setAttribute(key,value){this[key]=value;}focus(){this.focused=true;}scrollIntoView(){}
  addEventListener(type,callback){this['on'+type]=callback;}
}
const ids={};const fields={};
for(const id of ['trends-run','trends-toggle','trends-best','trends-status','trends-next','trends-results','trends-errors','trends-summary','trends-provider','manual-intake','workspace','automatic-message'])ids[id]=new Element();
for(const name of ['source_url','video','saved_source_path','dry_run','caption','research_keywords','rules','rights_notes'])fields[name]=new Element();
fields.rules.value='Campaign rules';fields.rights_notes.value='Permission notes';fields.caption.value='Required #ad';fields.video.value='old-file';fields.saved_source_path.value='uploads/old.mp4';
ids.intake={elements:{namedItem:name=>fields[name]}};
const document={getElementById:id=>ids[id],createElement:()=>new Element()};
const requests=[];let state={enabled:true,paused:false,interval_hours:6,provider:'public_search',next_scan_at:null,latest:null};let selectedJob;
const window={clipForm:{show:name=>{window.formStep=name;}},clipStudio:{refresh(){}},selectClippingJob:id=>{selectedJob=id;}};
const context={document,window,URL,Date,console,setInterval(){},matchMedia:()=>({matches:true}),fetch:async(url,options={})=>{
  requests.push({url,options});
  let data=state;
  if(url.endsWith('/preview'))data={id:'preview-job'};
  return {ok:true,json:async()=>data};
}};
const path='clipping/trends.js';assert.ok(fs.existsSync(path),'Trend section interaction script is missing');
vm.runInNewContext(fs.readFileSync(path,'utf8'),context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const texts=root=>[root.textContent,...root.children.flatMap(item=>typeof item==='string'?[item]:texts(item))].join(' ');
(async()=>{
 await tick();assert.match(ids['trends-results'].textContent,/scan|research/i);
 const item={id:'aaaaaaaaaaa',url:'https://www.youtube.com/watch?v=aaaaaaaaaaa',title:'<script>unsafe</script>',creator:'Creator',niches:['Gaming'],views:24000,published_at:'2026-10-09T00:00:00Z',observed_at:'2026-10-10T00:00:00Z',duration:300,views_per_hour_since_upload:1000,measured_growth_per_hour:null,eligible_preview:true};
 state={...state,latest:{id:'scan-id',status:'completed',created_at:'2026-10-10T00:00:00Z',updated_at:'2026-10-10T00:00:00Z',results:[item],failures:[],searched_niches:['Gaming'],ranking_note:'Signals, not a viral prediction'}};
 await window.trendResearch.refresh();assert.equal(ids['trends-best'].disabled,false);
 assert.match(texts(ids['trends-results']),/unsafe/);assert.match(texts(ids['trends-results']),/lifetime average/i);
 const row=ids['trends-results'].children[0];
 const descendants=root=>[root,...root.children.filter(child=>typeof child!=='string').flatMap(descendants)];
 const apply=descendants(row).find(element=>element.textContent==='Use source in campaign');assert.ok(apply);await apply.onclick();
 assert.equal(fields.source_url.value,item.url);assert.equal(fields.dry_run.checked,false);assert.equal(fields.video.value,'');assert.equal(fields.saved_source_path.value,'');
 assert.equal(fields.rules.value,'Campaign rules');assert.equal(fields.rights_notes.value,'Permission notes');assert.equal(fields.caption.value,'Required #ad');assert.equal(window.formStep,'source');
 await ids['trends-best'].onclick();assert.equal(selectedJob,'preview-job');assert.equal(requests.at(-1).options.method,'POST');
 state={...state,latest:{...state.latest,status:'retry_scheduled',next_attempt_at:'2026-10-10T01:00:00Z',results:[],failures:[{niche:'Gaming',message:'Connection unavailable'}]}};
 await window.trendResearch.refresh();assert.equal(ids['trends-best'].disabled,true);assert.match(ids['trends-status'].textContent,/retry|connection/i);assert.match(texts(ids['trends-errors']),/Connection unavailable/);
 state.enabled=false;await window.trendResearch.refresh();assert.match(ids['trends-toggle'].textContent,/Resume/i);
 console.log('Trend research UI source preservation, safe rendering, previews and retry states passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
