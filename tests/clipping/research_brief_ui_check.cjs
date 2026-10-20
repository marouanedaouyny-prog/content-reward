const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag='div') {this.tag=tag;this.children=[];this.value='';this.checked=false;this.files=[];}
  append(...items) {this.children.push(...items);}
  replaceChildren(...items) {this.children=items;}
  addEventListener(name, fn) {this[name]=fn;}
  setAttribute(name, value) {this[name]=value;}
  scrollIntoView() {}
  focus() {}
}
const fields=new Map(), elements=new Map();
const field=name=>{if(!fields.has(name))fields.set(name,new Element());return fields.get(name);};
const intake=new Element();intake.elements={namedItem:field};
const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const document={querySelector:selector=>selector==='#intake' ? intake : get(selector.slice(1)),
  getElementById:get,createElement:tag=>new Element(tag)};
const brief={topic:'gaming',keywords:['gaming'],target_duration:40,month:'2025-08',language:'en',country:'US',
  support_count:12,compared_cohorts:2,basis:'share_rate',median_share_rate:.08,
  can_apply:true,reason:'Compare similar posts.',note:'Historical experiment, not a prediction.'};
let report={source:'operator_sample',valid_records:24,matched_records:24,invalid_records:0,
  duplicate_records:0,empty_captions:0,cohorts:[],planning_brief:brief,brief_note:'',
  limitations:[],note:'Descriptive report'};
const window={};
vm.runInNewContext(fs.readFileSync('clipping/research.js','utf8'),{
  document,window,FormData,Blob,URL,setTimeout,
  fetch:async()=>({ok:true,json:async()=>report})});
const all=root=>[root,...root.children.flatMap(all)];
const apply=()=>all(get('metadata-report')).find(item=>item.tag==='button' && item.textContent==='Use brief for this campaign');
async function run() {
  get('metadata-file').files=[new Blob(['sample'])];
  await get('metadata-analyze').onclick();
  assert.equal(typeof apply()?.onclick,'function','Imported report should supply a usable brief');
  field('duration_min').value='15';field('duration_max').value='30';
  field('caption').value='Required campaign disclosure';field('source_url').value='https://youtu.be/abcdefghijk';
  field('language').value='en';field('aspect').value='1:1';
  apply().onclick();
  assert.equal(Number(field('duration').value),30,'Campaign maximum must bound the research target');
  assert.equal(field('research_keywords').value,'gaming');
  assert.equal(field('auto_clip').checked,true);
  assert.equal(field('caption').value,'Required campaign disclosure');
  assert.equal(field('source_url').value,'https://youtu.be/abcdefghijk');
  assert.equal(field('aspect').value,'1:1');
  assert.equal(get('manual-intake').open,true);
  field('language').value='ar';field('duration').value=22;
  apply().onclick();
  assert.equal(Number(field('duration').value),22,'A mismatched language must not change settings');
  assert(get('research-message').textContent.includes('language'));
  field('language').value='en';field('duration_min').value='50';
  apply().onclick();
  assert.equal(Number(field('duration').value),22,'Invalid campaign bounds must not change settings');
  field('duration_min').value='-1';
  apply().onclick();
  assert.equal(Number(field('duration').value),22,'A negative campaign minimum must not be hidden by clamping');
  report={...report,source:'synthetic_demo',planning_brief:{...brief,can_apply:false}};
  await get('metadata-demo').onclick();
  assert.equal(apply(),undefined,'Synthetic evidence cannot drive a real task');
  assert(get('research-map-status').textContent.includes('Synthetic'));
  get('open-research').onclick();
  assert.equal(get('manual-intake').open,true);
  assert.equal(get('research-tools').open,true);
  console.log('Research recommendations preserve source/disclosure, respect campaign bounds and exclude synthetic data.');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
