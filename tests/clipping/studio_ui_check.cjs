const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(id='') {
    this.id=id;this.value='';this.checked=false;this.files=[];this.dataset={};this.hidden=false;
    this.listeners={};this.valid=true;this.validationMessage='This field is required.';
    this.style={values:{},setProperty(name,value){this.values[name]=value;}};
  }
  setAttribute(name,value) {this[name]=value;}
  removeAttribute(name) {delete this[name];}
  addEventListener(name,fn) {this.listeners[name]=fn;}
  focus() {this.focused=true;}
  scrollIntoView() {this.scrolled=true;}
  checkValidity() {return this.valid;}
  reportValidity() {this.reported=true;return this.valid;}
  querySelectorAll() {return this.controls || [];}
}
const ids=new Map(),fields=new Map();
const get=id=>{if(!ids.has(id))ids.set(id,new Element(id));return ids.get(id);};
const field=name=>{if(!fields.has(name))fields.set(name,new Element(name));return fields.get(name);};
const names=['campaign','source','clip'];
const panes=names.map(name=>{const item=get('form-'+name);item.dataset.formPane=name;return item;});
const steps=names.map(name=>{const item=new Element();item.dataset.formStep=name;return item;});
const formats=['9:16','1:1','16:9'].map(format=>{const item=new Element();item.dataset.studioFormat=format;return item;});
const form=get('intake');form.elements={namedItem:field};
panes[0].controls=[field('title'),field('campaign_url'),field('rules'),field('rights_notes')];
panes[1].controls=[field('source_url'),field('language')];
panes[2].controls=[field('duration'),field('caption'),field('aspect')];
field('title').valid=false;field('dry_run').checked=true;field('duration').value='30';
field('aspect').value='9:16';field('caption').value='Keep this campaign disclosure.';
get('studio-angle').value='-18';
const media={matches:false,addEventListener(name,fn){this[name]=fn;}};
const document={getElementById:get,querySelector:selector=>get(selector.slice(1)),
  querySelectorAll:selector=>selector==='[data-form-pane]' ? panes : selector==='[data-form-step]' ? steps : formats};
const window={matchMedia:()=>media};
vm.runInNewContext(fs.readFileSync('clipping/studio.js','utf8'),{document,window});
assert.equal(panes[0].hidden,false);assert.equal(panes[1].hidden,true);assert.equal(panes[2].hidden,true);
get('form-next').onclick();
assert.equal(panes[0].hidden,false,'Invalid required campaign fields must block moving forward');
assert.equal(field('title').focused,true);
field('title').valid=true;get('form-next').onclick();
assert.equal(panes[1].hidden,false);
field('dry_run').checked=false;get('form-next').onclick();
assert.equal(panes[1].hidden,false,'A live source step needs exactly one source');
field('source_url').value='https://youtu.be/abcdefghijk';get('form-next').onclick();
assert.equal(panes[2].hidden,false);
assert.equal(get('review-submit').hidden,false);
get('form-back').onclick();assert.equal(panes[1].hidden,false);
assert.equal(field('caption').value,'Keep this campaign disclosure.');
formats[1].onclick();
assert.equal(field('aspect').value,'9:16','Inspecting a model must not change a task');
assert(get('studio-format-label').textContent.includes('1080 × 1080'));
get('studio-use-format').onclick();
assert.equal(field('aspect').value,'1:1');assert.equal(panes[2].hidden,false);
assert.equal(get('manual-intake').open,true);
assert.equal(field('caption').value,'Keep this campaign disclosure.');
field('title').valid=false;
assert.equal(window.clipForm.validate(),false,'Final submission must check hidden earlier steps');
assert.equal(panes[0].hidden,false);
field('title').valid=true;field('source_url').valid=false;
assert.equal(window.clipForm.validate(),false);assert.equal(panes[1].hidden,false);
field('source_url').valid=true;
assert.equal(window.clipForm.validate(),true);
get('studio-angle').value='1000';get('studio-angle').oninput();
assert.equal(get('studio-model').style.values['--view-angle'],'30deg');
media.matches=true;media.change();
assert.equal(get('studio-model').style.values['--view-angle'],'0deg');
assert.equal(get('studio-angle').disabled,true);
assert(get('studio-motion-note').textContent.includes('Reduced motion'));
console.log('Guided steps validate hidden fields; studio format changes require apply, preserve disclosure and honor reduced motion.');
