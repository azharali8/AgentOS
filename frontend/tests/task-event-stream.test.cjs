const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
test('event hook deduplicates, orders and rejects stale task delivery after switching',()=>{
 let index=0;const slots=[],pending=[],sockets=[];
 const react={useMemo:(fn,deps)=>{const i=index++;const old=slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j]))slots[i]={deps,value:fn()};return slots[i].value;},useState:initial=>{const i=index++;if(!(i in slots))slots[i]=initial;return [slots[i],value=>slots[i]=typeof value==='function'?value(slots[i]):value];},useEffect:(fn,deps)=>{const i=index++;const old=slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j])){old?.cleanup?.();const entry={deps};slots[i]=entry;pending.push(()=>entry.cleanup=fn());}}};
 class Socket{static OPEN=1;constructor(url){this.url=url;sockets.push(this);}close(){this.closed=true;}send(){}}
 const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../hooks/useTaskEventStream.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{exports,require:()=>react,URL,process:{env:{}},WebSocket:Socket,setInterval:()=>1,clearInterval(){},setTimeout:()=>1,clearTimeout(){}});
 const render=id=>{index=0;return exports.useTaskEventStream(id,'session');};const flush=()=>pending.splice(0).forEach(fn=>fn());
 render('a');flush();const a=sockets[0];
 const event=(id,time,task='a')=>({event_id:id,task_id:task,event_type:'FILE_READ',timestamp:`2026-10-08T10:00:0${time}Z`,payload:{path:'a.py'}});
 for(const value of [event('late',2),event('early',1),event('late',2),event('other',0,'b'),{event_id:'malformed',task_id:'a'}])a.onmessage({data:JSON.stringify(value)});
 assert.deepEqual(Array.from(render('a').events,e=>e.event_id),['early','late']);
 const stable=render('a').events;assert.equal(render('a').events,stable,'unchanged events must retain identity to avoid effect loops');
 assert.equal(render('b').events.length,0);flush();assert.equal(a.closed,true);
 a.onmessage({data:JSON.stringify(event('stale',3))});sockets[1].onmessage({data:JSON.stringify(event('new',4,'b'))});
 assert.deepEqual(Array.from(render('b').events,e=>e.event_id),['new']);
});
