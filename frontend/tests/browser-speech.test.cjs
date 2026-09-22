const {test} = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
function setup() {
  const timers = new Map(); let id = 0;
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require('node:path').join(__dirname, '../lib/browser-speech.ts'),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,
    {exports, setTimeout:(fn)=>{timers.set(++id,fn);return id;}, clearTimeout:key=>timers.delete(key)});
  const spoken=[], states=[], errors=[], starts=[];
  const synth={paused:true,cancel(){},resume(){this.paused=false;},getVoices(){return [];},speak(u){spoken.push(u);}};
  const p=new exports.BrowserSpeech(synth,text=>({text}),v=>states.push(v),v=>errors.push(v),v=>starts.push(v));
  return {p,spoken,states,errors,starts,timers,synth};
}
test('Speaking begins only on actual browser start and ends on end',()=>{
  const s=setup();s.p.speak('hello');assert.equal(s.states.at(-1),false);
  assert.equal(s.synth.paused,false);s.spoken[0].onstart();assert.equal(s.states.at(-1),true);
  s.spoken[0].onend();assert.equal(s.states.at(-1),false);assert.equal(s.timers.size,0);
});
test('stalled start and stalled playback fail visibly without staying Speaking',()=>{
  for(const started of [false,true]) {
    const s=setup();s.p.speak('hello');if(started)s.spoken[0].onstart();
    [...s.timers.values()][0]();assert.equal(s.states.at(-1),false);assert.equal(s.errors.length,1);
  }
});
test('barge-in stop and replacement invalidate all old playback callbacks',()=>{
  const s=setup();s.p.speak('old');const old=s.spoken[0];old.onstart();s.p.stop();
  s.p.speak('new');s.spoken[1].onstart();old.onend();old.onerror();
  assert.equal(s.states.at(-1),true);assert.equal(s.errors.length,0);
  s.p.stop();s.spoken[1].onstart();assert.equal(s.states.at(-1),false);
});
test('browser synthesis exceptions produce a visible fallback',()=>{
  const s=setup();s.synth.speak=()=>{throw new Error('unavailable');};s.p.speak('hello');
  assert.equal(s.errors.length,1);assert.equal(s.states.at(-1),false);
});
