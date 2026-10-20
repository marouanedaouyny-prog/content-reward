// Exercise the real UI handoff without a browser process: an alternative cut
// must carry its source/campaign instead of using an unrelated intake form.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() {this.children=[];this.value='';this.checked=false;this.files=[];}
  append(...items) {this.children.push(...items);}
  replaceChildren(...items) {this.children=items;}
  addEventListener(name, fn) {this[name]=fn;}
  setAttribute(name, value) {this[name]=value;}
  scrollIntoView(options) {this.scrollOptions=options;}
  focus() {}
}
const fields=new Map();
const field=name=>{if(!fields.has(name))fields.set(name,new Element());return fields.get(name);};
const ids=new Map();
const document={querySelector:selector=>selector==='#intake' ? {elements:{namedItem:field}} : document.getElementById(selector.slice(1)),
  getElementById:id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);},
  createElement:()=>new Element()};
const window={matchMedia:()=>({matches:true})};
vm.runInNewContext(fs.readFileSync('clipping/research.js','utf8'),
  {document,window,FormData,Blob,URL,setTimeout,
    fetch:async()=>({ok:false,json:async()=>({detail:'Source lookup unavailable; use an upload.'})})});
field('source_url').value='https://youtube.com/watch?v=unrelated01';
field('title').value='An unrelated campaign';
const payload={campaign:{title:'Original campaign',url:'https://example.com/campaign',platform:'tiktok',
  rules:'Keep context',rights_notes:'Authorized source',duration_min:15,duration_max:40,
  pre_post_review:true},source_path:'uploads/original.mp4',dry_run:false,
  caption:'Required disclosure',language:'en',transcript_srt:'original timed transcript'};
const idea={clip_plan:{start_seconds:20,duration_seconds:30,aspect_ratio:'1:1'},
  source_excerpt:'A complete source moment.',reasons:['Source boundaries'],editorial_score:50,
  note:'Heuristic only',caption:'Suggestion'};
const container=new Element();window.renderClipIdeas(container,[idea],payload);
const button=container.children[0].children.at(-1);button.onclick();
assert.equal(field('title').value,'Original campaign');
assert.equal(field('source_url').value,'');
assert.equal(field('saved_source_path').value,'uploads/original.mp4');
assert.equal(field('caption').value,'Required disclosure');
assert.equal(field('start').value,20);
assert.equal(field('aspect').value,'1:1');
assert.equal(field('auto_clip').checked,false);
assert.equal(field('pre_post_review').checked,true);
assert.equal(field('dry_run').checked,false);
assert.equal(document.getElementById('manual-intake').open,true,'An alternative cut must open the campaign form it fills');
assert.equal(field('start').scrollOptions.behavior,'auto','Reduced motion must suppress smooth scrolling');
field('source_url').change();
assert.equal(field('saved_source_path').value,'');
field('caption').value='';
let modelCaption;
window.clipStudio={refresh(){modelCaption=field('caption').value;}};
const other=new Element();window.renderClipIdeas(other,[idea]);
other.children[0].children.at(-1).onclick();
assert.equal(modelCaption,'Suggestion','The layout model must refresh after a suggested caption is filled');
console.log('Alternative-cut handoff preserves source, campaign and disclosure; changing the source clears reuse.');
document.getElementById('source-check').onclick().then(()=>{
  assert.equal(document.getElementById('source-details').textContent,'Source lookup unavailable; use an upload.');
  console.log('Source lookup failure remains visible beside the source controls.');
}).catch(error=>{console.error(error);process.exitCode=1;});
