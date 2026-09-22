const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');const ts=require('typescript');const React=require('react');
function load(file,requires={},globals={}){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{exports,require:n=>requires[n]??require(n),TextEncoder,TextDecoder,...globals});return exports;}
function hooks(){let index=0;const values=[],effects=[];return {react:{...React,useState:v=>{const i=index++;if(!(i in values))values[i]=v;return [values[i],v=>values[i]=v];},useRef:v=>{const i=index++;if(!(i in values))values[i]={current:v};return values[i];},useEffect:(fn,deps)=>{const i=index++;const prev=values[i];if(!prev||deps.some((d,j)=>d!==prev.deps[j])){prev?.cleanup?.();const entry={deps};values[i]=entry;effects.push(()=>entry.cleanup=fn());}},useCallback:(fn,deps)=>{const i=index++;const prev=values[i];if(!prev||deps.some((d,j)=>d!==prev.deps[j]))values[i]={deps,fn};return values[i].fn;}},render:fn=>{index=0;return fn();},flush:()=>{effects.splice(0).forEach(fn=>fn());}};}
function find(n,p){if(!n||typeof n!=='object')return null;if(p(n))return n;for(const c of React.Children.toArray(n.props?.children)){const found=find(c,p);if(found)return found;}return null;}
const composer=load('../lib/composer.ts');const theme=load('../lib/theme.ts');
test('text submission keys preserve multiline and IME input',()=>{assert.equal(composer.shouldSubmit('Enter',false,false),true);assert.equal(composer.shouldSubmit('Enter',true,false),false);assert.equal(composer.shouldSubmit('Enter',false,true),false);});
test('attachments accept bounded UTF8 source and reject binary, traversal and oversized content',async()=>{const file=(name,content,size)=>({name,size:size??Buffer.byteLength(content),arrayBuffer:async()=>new TextEncoder().encode(content).buffer});assert.equal((await composer.readAttachment(file('hello.py','print(1)'))).content,'print(1)');for(const f of [file('../secret.py','x'),file('.env','x'),file('a.pdf','x'),file('a.py','\0'),file('a.py','x',32769)])await assert.rejects(composer.readAttachment(f));});
test('Light default, Dark and System resolution',()=>{assert.equal(theme.savedTheme(null),'light');assert.equal(theme.resolvedTheme('dark',false),'dark');assert.equal(theme.resolvedTheme('system',true),'dark');assert.equal(theme.resolvedTheme('system',false),'light');});
test('theme preference persists and System responds to changes',async()=>{
 const h=hooks(),store=new Map(),listeners=new Set(),media={matches:false,addEventListener:(_,fn)=>listeners.add(fn),removeEventListener:(_,fn)=>listeners.delete(fn)},document={documentElement:{dataset:{}}};
 const {useWorkspaceSettings}=load('../hooks/useWorkspaceSettings.ts',{'react':h.react,'../lib/api':{},'../lib/theme':theme},{document,matchMedia:()=>media,localStorage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v)}});
 const client={};let state=h.render(()=>useWorkspaceSettings(client,false));h.flush();state.setTheme('dark');state=h.render(()=>useWorkspaceSettings(client,false));h.flush();assert.equal(document.documentElement.dataset.theme,'dark');assert.equal(store.get('agentos_theme'),'dark');
 state.setTheme('system');state=h.render(()=>useWorkspaceSettings(client,false));h.flush();assert.equal(document.documentElement.dataset.theme,'light');media.matches=true;listeners.forEach(fn=>fn());assert.equal(document.documentElement.dataset.theme,'dark');
});
test('composer sends real client request once and removes attachment chips',async()=>{
 const h=hooks(),calls=[],created=[];
 const {CommandComposer}=load('../components/CommandComposer.tsx',{'react':h.react,'lucide-react':new Proxy({},{get:()=>()=>null}),'../lib/api':{},'../hooks/useWorkspaceSettings':{},'./SettingsView':{ModelSelector:()=>null},'./voice/VoiceControl':{VoiceControl:()=>null},'../lib/voice-stream':{supervisorStage:()=>''},'../lib/composer':composer},{setInterval:()=>1,clearInterval:()=>{}});
 const props={client:{createTask:async(...args)=>{calls.push(args);return {task_id:'real-client-id'};}},preferences:{},onTaskCreated:id=>created.push(id)};
 let tree=h.render(()=>CommandComposer(props));const upload=find(tree,n=>n.type==='input');
 await upload.props.onChange({target:{files:[{name:'requirements.txt',size:4,arrayBuffer:async()=>new TextEncoder().encode('test').buffer}],value:''}});
 tree=h.render(()=>CommandComposer(props));assert.ok(find(tree,n=>n.props['aria-label']==='Remove requirements.txt'));
 find(tree,n=>n.props['aria-label']==='Remove requirements.txt').props.onClick();tree=h.render(()=>CommandComposer(props));assert.equal(find(tree,n=>n.props['aria-label']==='Remove requirements.txt'),null);
 find(tree,n=>n.type==='textarea').props.onChange({target:{value:'Build something\nwith tests',style:{},scrollHeight:100}});tree=h.render(()=>CommandComposer(props));const send=find(tree,n=>n.props['aria-label']==='Send to Supervisor');await Promise.all([send.props.onClick(),send.props.onClick()]);await new Promise(setImmediate);assert.equal(calls.length,1);assert.equal(calls[0][0],'Build something\nwith tests');assert.equal(created[0],'real-client-id');
});
test('settings and Workspace share a visible model menu with exact model selection',()=>{
 const h=hooks();let selected,signedOut=false;
 const {ModelSelector}=load('../components/ModelSelector.tsx',{'react':h.react,'../lib/model-label':load('../lib/model-label.ts')});
 const {SettingsView}=load('../components/SettingsView.tsx',{'./ModelSelector':{ModelSelector},'../lib/model-label':load('../lib/model-label.ts')});
 const preferences={theme:'light',models:{active_model:'coder:3b',status:'online',selection_enabled:true,models:[{name:'coder:3b',selectable:true},{name:'other:3b',selectable:true},{name:'embed',selectable:false,status:'Not a chat model'}]},select:m=>selected=m,readAloud:true};
 const tree=SettingsView({user:{username:'Engineer',email:'engineer@example.test',role:'USER'},preferences,onSignOut:()=>signedOut=true});find(tree,n=>n.type==='button'&&n.props.children==='Sign out').props.onClick();assert.ok(signedOut);
 const render=()=>h.render(()=>ModelSelector({preferences}));
 find(render(),n=>n.props['aria-haspopup']==='listbox').props.onClick();
 let menu=render();assert.ok(find(menu,n=>n.props.role==='listbox'));
 assert.equal(find(menu,n=>n.props.role==='option'&&n.props.children[0].props.children==='embed'),null);
 find(menu,n=>n.props.role==='option'&&n.props.children[0].props.children==='other:3b').props.onClick();assert.equal(selected,'other:3b');
 preferences.models.active_model=selected;menu=render();assert.equal(find(menu,n=>n.props.role==='listbox'),null);
 assert.ok(find(menu,n=>n.type==='span'&&n.props.children==='other:3b'));
});

test('model picker exposes loading and retry instead of an invisible disabled selector',()=>{
 const h=hooks();let refreshed=0;
 const {ModelSelector}=load('../components/ModelSelector.tsx',{'react':h.react,'../lib/model-label':load('../lib/model-label.ts')});
 const preferences={models:null,busy:true,refresh:()=>refreshed++};const render=()=>h.render(()=>ModelSelector({preferences}));
 let tree=render();const trigger=find(tree,n=>n.props['aria-haspopup']==='listbox');assert.equal(trigger.props.disabled,false);trigger.props.onClick();
 tree=render();assert.ok(find(tree,n=>n.props.role==='status'));preferences.busy=false;
 tree=render();find(tree,n=>n.props.className==='model-refresh').props.onClick();assert.equal(refreshed,1);
});

async function voiceHarness(){
 const h=hooks(),sent=[],spoken=[],tracks=[];let cancelled=0;const sockets=[];
 const track={stop(){tracks.push('stopped');},onended:null};
 const media={getTracks:()=>[track],getAudioTracks:()=>[track]};
 class AudioContext {constructor(){this.destination={};}async resume(){}audioWorklet={addModule:async()=>{}};createMediaStreamSource(){return {connect(){}};}async close(){}}
 class Worklet {constructor(){this.port={};}connect(){}disconnect(){}}
 const globals={navigator:{mediaDevices:{getUserMedia:async()=>media}},window:{AudioContext,AudioWorkletNode:Worklet,speechSynthesis:{cancel(){cancelled++;},resume(){},getVoices(){return [];},speak(u){spoken.push(u);u.onstart?.();}}},AudioContext,AudioWorkletNode:Worklet,SpeechSynthesisUtterance:class{constructor(text){this.text=text;}},WebSocket:{OPEN:1},crypto:{randomUUID:()=> 'test-session'},setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){},DOMException};
 const stream=load('../lib/voice-stream.ts');const speech=load('../lib/browser-speech.ts',{},globals);
 const {VoiceControl}=load('../components/voice/VoiceControl.tsx',{'react':h.react,'lucide-react':new Proxy({},{get:()=>()=>null}),'../../lib/api':{},'../../lib/voice-stream':stream,'../../lib/browser-speech':speech},globals);
 const client={openVoiceStream(id,mode){const ws={mode,readyState:1,bufferedAmount:0,send:m=>sent.push(m),close(){}};sockets.push(ws);return ws;}};
 const render=()=>h.render(()=>VoiceControl({client}));render();h.flush();
 return {render,h,sockets,spoken,tracks,sent,cancelled:()=>cancelled,settle:()=>new Promise(setImmediate)};
}
test('one-shot microphone releases audio at final and never speaks or replays duplicate results',async()=>{
 const v=await voiceHarness();find(v.render(),n=>n.props['aria-label']==='One-shot voice command').props.onClick();await v.settle();v.render();v.h.flush();const ws=v.sockets[0];assert.equal(ws.mode,'once');
 const event=m=>ws.onmessage({data:JSON.stringify(m)});event({type:'Begin'});event({type:'Turn',transcript:'partial',end_of_turn:false,turn_order:0});assert.equal(v.tracks.length,0);
 event({type:'Turn',transcript:'Run tests',end_of_turn:true,turn_order:0});assert.equal(v.tracks.length,1);
 event({type:'Result',turn_order:0,status:'completed',tts_summary:'Done'});event({type:'Result',turn_order:0,status:'completed',tts_summary:'Done'});assert.equal(v.spoken.length,0);assert.ok(v.sent.includes('{"type":"Stop"}'));
});
test('Live Voice supports TTS, barge-in and explicit stop in the same composer',async()=>{
 const v=await voiceHarness();find(v.render(),n=>n.props['aria-label']==='Start Live Voice').props.onClick();await v.settle();v.render();v.h.flush();const ws=v.sockets[0];assert.equal(ws.mode,'live');const event=m=>ws.onmessage({data:JSON.stringify(m)});
 event({type:'Begin'});event({type:'Turn',transcript:'Status',end_of_turn:true,turn_order:0});event({type:'Processing',turn_order:0});event({type:'Result',turn_order:0,status:'completed',tts_summary:'Ready'});assert.equal(v.spoken.length,1);const before=v.cancelled();event({type:'SpeechStarted'});assert.ok(v.cancelled()>before);
 event({type:'Result',turn_order:0,status:'completed',tts_summary:'stale'});assert.equal(v.spoken.length,1);
 find(v.render(),n=>n.props['aria-label']==='End Live Voice').props.onClick();assert.ok(v.sent.includes('{"type":"Stop"}'));assert.equal(v.tracks.length,1);
});


test('short model names retain distinct Kimi versions and collapse Llama labels',()=>{
 const {modelLabel}=load('../lib/model-label.ts');
 assert.equal(modelLabel('llama3.2:latest'),modelLabel('llama3.2:3b'));
 assert.notEqual(modelLabel('kimi-k3:cloud'),modelLabel('kimi-k2.6:cloud'));
 assert.equal(modelLabel('qwen3.5:397b-cloud'),'Qwen 3.5');
});

test('approvals enforce role in UI and display server failures instead of silently failing',async()=>{
 for(const role of ['USER','DEVELOPER']) {
  const h=hooks();let calls=0;
  const client={listApprovals:async()=>[{approval_id:'pending',status:'PENDING',tool_name:'apply_patch',reason:'Review patch'}],listTasks:async()=>[],resolveApproval:async()=>{calls++;throw {status:403};}};
  const {ApprovalCenterView}=load('../components/approvals/ApprovalCenterView.tsx',{'react':{...h.react,default:h.react},'lucide-react':new Proxy({},{get:()=>()=>null})});
  const render=()=>h.render(()=>ApprovalCenterView({client,userRole:role}));render();h.flush();await new Promise(setImmediate);
  let tree=render();const approve=find(tree,n=>n.type==='button'&&n.props.children==='Approve & Apply');
  assert.equal(approve.props.disabled,role==='USER');await approve.props.onClick();tree=render();
  assert.equal(calls,role==='USER'?0:1);
  if(role==='DEVELOPER')assert.ok(find(tree,n=>n.props.role==='alert'));
 }
});


test('provider turn numbering resets on reconnect and partial speech interrupts TTS without executing',async()=>{
 const v=await voiceHarness();find(v.render(),n=>n.props['aria-label']==='Start Live Voice').props.onClick();await v.settle();v.render();v.h.flush();const ws=v.sockets[0];const event=m=>ws.onmessage({data:JSON.stringify(m)});
 const complete=()=>{event({type:'Turn',transcript:'Status',end_of_turn:true,turn_order:0});event({type:'Processing',turn_order:0});event({type:'Result',turn_order:0,status:'completed',tts_summary:'Ready'});};
 event({type:'Begin'});complete();assert.equal(v.spoken.length,1);
 const before=v.cancelled();event({type:'Turn',transcript:'Another',end_of_turn:false,turn_order:1});assert.ok(v.cancelled()>before);assert.equal(v.spoken.length,1);
 event({type:'Begin'});complete();assert.equal(v.spoken.length,2);
});
