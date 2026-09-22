const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const ts=require('typescript');const vm=require('node:vm');const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
function load(file,requires={}){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{exports,require:n=>requires[n]??require(n)});return exports;}
const mapper=load('../lib/engineering-stream.ts');const {engineeringEntries,patchFiles,shouldFollowStream}=mapper;
const {EngineeringStream}=load('../components/EngineeringStream.tsx',{'../lib/engineering-stream':mapper,'lucide-react':new Proxy({},{get:()=>props=>React.createElement('svg',props)})});
const task={task_id:'t',instruction:'Create endpoint',status:'EXECUTING',created_at:'2026-09-21T10:00:00Z'};
const event=(type,payload={},second=1,id=type)=>({task_id:'t',event_id:id,event_type:type,payload,timestamp:`2026-09-21T10:00:${String(second).padStart(2,'0')}Z`});
const render=(events=[],extra={})=>renderToStaticMarkup(React.createElement(EngineeringStream,{task,events,artifacts:[],approval:null,client:{},isStreaming:true,onResolved(){},onViewFile(){},...extra}));
test('real event mapping is ordered, deduplicated and excludes invented stages and private reasoning',()=>{
 const events=[event('FILE_READ',{path:'main.py'},3),event('PLAN_CREATED',{},2),event('TASK_CREATED',{},1),event('TASK_CREATED',{},1,'duplicate'),event('AGENT_PROTOCOL_MESSAGE',{reasoning:'PRIVATE'},4)];
 const rows=engineeringEntries(task,[...events,events[0]],[]);assert.deepEqual(Array.from(rows,r=>r.title),['Request received','Planning work','Read main.py']);assert.ok(!JSON.stringify(rows).includes('PRIVATE'));
 const html=render(events);assert.ok(!html.includes('Running tests'));assert.ok(!html.includes('Preparing fixes'));assert.match(html,/Read main.py/);
});
test('only observed in-flight operation animates and completion collapses details',()=>{
 const start=event('SUBTASK_STARTED',{subtask_id:'s',agent:'testing'});let html=render([start]);assert.match(html,/engineering-active/);assert.match(html,/Running tests/);
 html=render([start,event('SUBTASK_COMPLETED',{subtask_id:'s',agent_type:'testing',status:'completed',summary:'Actual result'},2)]);assert.ok(!html.includes('engineering-active'));assert.ok(!html.includes('open=""'));assert.match(html,/Actual result/);
});
test('patch previews contain only real hunks and correct line counts',()=>{
 const content={patch_id:'p',files:[{relative_path:'main.py',hunks:[{lines:[' context\n','-old\n','+new\n','+next\n']}]}]};
 const art={artifact_id:'a',task_id:'t',artifact_type:'PATCH',created_at:task.created_at,content};
 const file=patchFiles(content)[0];assert.equal(file.added,2);assert.equal(file.removed,1);
 const html=render([event('PATCH_CREATED',{patch_id:'p'})],{artifacts:[art]});assert.match(html,/View full diff/);assert.match(html,/new/);assert.match(html,/main.py/);assert.match(html,/PATCH/);
});
test('test failure displays grounded command, counts and output without claiming success',()=>{
 const html=render([event('TEST_COMPLETED',{report:{passed:false,command:['python','-m','pytest','-q'],passed_count:2,failed_count:1,duration_seconds:1.2,raw_stdout:'tests/test_api.py:31 AssertionError',issues:[{title:'AssertionError',test_file:'tests/test_api.py',line:31,error_message:'expected 200'}]}})]);
 assert.match(html,/python -m pytest -q/);assert.match(html,/2 passed/);assert.match(html,/1 failed/);assert.match(html,/tests\/test_api.py:31/);assert.match(html,/View terminal output/);assert.ok(!html.includes('Tests passed'));
});
test('diagnosis and review show allowed summary fields only',()=>{
 const arts=['DIAGNOSIS','REVIEW'].map((kind,i)=>({artifact_id:String(i),task_id:'t',artifact_type:kind,created_at:task.created_at,content:{summary:'Grounded summary',root_cause:'Missing route',suggested_fix:'Register route',approved:false,reasoning:'PRIVATE_REASONING'}}));
 const html=render([],{artifacts:arts});assert.match(html,/Grounded summary/);assert.match(html,/Register route/);assert.ok(!html.includes('PRIVATE_REASONING'));
});
test('inline approval is task-bound and role protected',()=>{
 const approval={task_id:'t',approval_id:'a',status:'PENDING',arguments_summary:{files:['main.py']}};
 const events=[event('APPROVAL_REQUIRED',{approval_id:'a'})];
 assert.match(render(events,{approval,userRole:'DEVELOPER'}),/Approve &amp; Apply/);
 assert.match(render(events,{approval,userRole:'VIEWER'}),/disabled/);
 assert.ok(!render(events,{approval:{...approval,task_id:'other'},userRole:'DEVELOPER'}).includes('Approve &amp; Apply'));
});
test('failed application and failed task stay failed, and terminal entries do not animate',()=>{
 const html=render([event('PATCH_APPLIED',{applied:false,files:['main.py']}),event('SUBTASK_STARTED',{agent:'coding',subtask_id:'s'})],{task:{...task,status:'FAILED',error:'Model returned invalid output'}});
 assert.match(html,/Patch application failed/);assert.match(html,/Execution stopped/);assert.match(html,/Model returned invalid output/);assert.ok(!html.includes('engineering-active'));assert.ok(!html.includes('Changed files'));
});
test('scroll follows only near bottom, preserving reading older work',()=>{assert.equal(shouldFollowStream(0,1000,500),false);assert.equal(shouldFollowStream(480,1000,500),true);});
test('no-event initial state indicates awaiting real Supervisor events',()=>{assert.match(render(),/Waiting for Supervisor activity/);assert.ok(!render().includes('Running tests'));});

test('approval submits the current approval once and continues in place with real events',async()=>{
 let cursor=0;const state=[];const mockReact={...React,useMemo:fn=>fn(),useState:value=>{const i=cursor++;if(!(i in state))state[i]=value;return [state[i],v=>state[i]=v];}};
 const {EngineeringStream:Stream}=load('../components/EngineeringStream.tsx',{'react':mockReact,'../lib/engineering-stream':mapper,'lucide-react':new Proxy({},{get:()=>()=>null})});
 const calls=[];let refreshed=0;
 const props={task,events:[event('APPROVAL_REQUIRED',{approval_id:'a'})],artifacts:[],approval:{approval_id:'a',task_id:'t',status:'PENDING',arguments_summary:{}},userRole:'DEVELOPER',client:{resolveApproval:async(...args)=>calls.push(args)},onResolved:()=>refreshed++,onViewFile(){},isStreaming:true};
 const draw=()=>{cursor=0;return Stream(props);};
 const find=(node,p)=>{if(!node||typeof node!=='object')return null;if(p(node))return node;for(const c of React.Children.toArray(node.props?.children)){const found=find(c,p);if(found)return found;}return null;};
 find(draw(),n=>n.type==='button'&&n.props.className==='engineering-approve').props.onClick();await new Promise(setImmediate);
 assert.deepEqual(calls,[['a',true]]);assert.equal(refreshed,1);assert.equal(find(draw(),n=>n.props?.className==='engineering-approve'),null);
 props.events.push(event('PATCH_APPLIED',{applied:true,files:['main.py']},3));assert.ok(find(draw(),n=>n.type==='span'&&n.props.children==='Changes applied'));
});

test('failed coding does not claim changes were proposed',()=>{const rows=mapper.engineeringEntries({...task,status:'FAILED'},[event('SUBTASK_FAILED',{agent:'coding',subtask_id:'s',error:'Invalid target'})],[]);assert.equal(rows.find(r=>r.id==='subtask:s').title,'Implementation stopped');});
