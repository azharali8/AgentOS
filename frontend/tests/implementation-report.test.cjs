const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function load(file,requires={}){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{exports,require:n=>requires[n]??require(n)});return exports;}
const mapper=load('../lib/engineering-stream.ts');
const {ImplementationReportView}=load('../components/ImplementationReport.tsx',{'../lib/engineering-stream':mapper});
const base={report_id:'implementation:t',task_id:'t',status:'FAILED',task_status:'FAILED',summary:'Task failed.',changes:[],files_changed:[],commands:[],tools:[],tests:[],approvals:[],reviews:[],artifacts:[],remaining_issues:['Retest failed'],warnings:[]};
const render=report=>renderToStaticMarkup(React.createElement(ImplementationReportView,{report}));
test('failed report never presents a successful implementation or fabricated review',()=>{const html=render(base);assert.match(html,/FAILED/);assert.match(html,/Retest failed/);assert.match(html,/No test results recorded/);assert.doesNotMatch(html,/Implementation complete|Review approved|No unresolved issues/);});
test('report renders exact applied line counts, individual failed runs and artifact references',()=>{const html=render({...base,files_changed:[{path:'app.py',additions:2,deletions:1,diffs:['patch']}],tests:[{artifact_id:'test',passed:false,passed_count:8,failed_count:1,exit_code:1,skipped_count:null}],approvals:[{approval_id:'approval',status:'APPROVED'}],artifacts:[{artifact_id:'patch',label:'Patch'}]});assert.match(html,/app.py/);assert.match(html,/\+2/);assert.match(html,/8 passed · 1 failed/);assert.match(html,/View diff/);assert.match(html,/APPROVED/);assert.equal((html.match(/data-report-id=/g)||[]).length,1);});
test('unknown line counts stay unknown and terminal warnings remain visible',()=>{const html=render({...base,status:'COMPLETED_WITH_WARNINGS',files_changed:[{path:'old.py',additions:null,deletions:null,diffs:[]}],warnings:['Earlier test run failed']});assert.doesNotMatch(html,/applied patch lines/);assert.match(html,/COMPLETED WITH WARNINGS/);assert.match(html,/Earlier test run failed/);});

test('artifact controls open the exact associated artifact',()=>{
 const opened=[];const tree=ImplementationReportView({report:{...base,artifacts:[{artifact_id:'actual-id',label:'Context'}]},onOpenArtifact:id=>opened.push(id)});
 const visit=node=>{if(!node||typeof node!=='object')return;if(node.type==='button')node.props.onClick();React.Children.forEach(node.props?.children,visit);};visit(tree);
 assert.deepEqual(opened,['actual-id']);
});

test('report reload replaces one report and ignores delayed responses from another task',async()=>{
 let index=0;const slots=[],effects=[],requests=[];
 const hooks={...React,useState:initial=>{const i=index++;if(!(i in slots))slots[i]=initial;return [slots[i],value=>slots[i]=typeof value==='function'?value(slots[i]):value];},useEffect:(fn,deps)=>{const i=index++,old=slots[i];if(!old||deps.some((d,j)=>d!==old.deps[j])){old?.cleanup?.();const entry={deps};slots[i]=entry;effects.push(()=>entry.cleanup=fn());}}};
 const {SessionImplementationReport}=load('../components/ImplementationReport.tsx',{'../lib/engineering-stream':mapper,react:hooks});
 const client={getImplementationReport:id=>new Promise(resolve=>requests.push({id,resolve}))};
 const draw=(id,revision='1')=>{index=0;const tree=SessionImplementationReport({client,taskId:id,revision});effects.splice(0).forEach(fn=>fn());return tree;};
 const settle=async()=>{await Promise.resolve();await Promise.resolve();};
 draw('a');draw('b');requests[0].resolve({...base,task_id:'a'});await settle();assert.match(renderToStaticMarkup(draw('b')),/Loading recorded/);
 requests[1].resolve({...base,task_id:'b',report_id:'implementation:b'});await settle();let html=renderToStaticMarkup(draw('b'));assert.equal((html.match(/data-report-id=/g)||[]).length,1);assert.match(html,/implementation:b/);
 draw('b','2');requests[2].resolve({...base,task_id:'b',report_id:'implementation:b'});await settle();html=renderToStaticMarkup(draw('b','2'));assert.equal((html.match(/data-report-id=/g)||[]).length,1);assert.doesNotMatch(html,/implementation:a/);
});
