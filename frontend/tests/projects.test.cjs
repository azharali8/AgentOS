const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function load(file,requires={}){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{exports,require:n=>requires[n]??(n==='lucide-react'?new Proxy({},{get:()=>props=>React.createElement('svg',props)}):require(n))});return exports;}
const {ProjectsSidebar}=load('../components/ProjectsSidebar.tsx');
const props={projects:[{project_id:'a',name:'Project A'},{project_id:'b',name:'Project B'}],conversations:[{project_id:'a',conversation_id:'ca',title:'Fix A tests'},{project_id:'b',conversation_id:'cb',title:'Private B work'}],activeProject:'a',activeConversation:'ca',busy:false,error:'',onProject(){},onConversation(){},onNewProject(){},onNewConversation(){},onRetry(){}};
test('Projects sidebar scopes conversations to the selected project',()=>{
 const html=renderToStaticMarkup(React.createElement(ProjectsSidebar,props));
 assert.match(html,/Fix A tests/);assert.doesNotMatch(html,/Private B work/);assert.match(html,/aria-current="page"/);assert.doesNotMatch(html,/Chat History/);
 const switched=renderToStaticMarkup(React.createElement(ProjectsSidebar,{...props,activeProject:'b',activeConversation:'cb'}));
 assert.match(switched,/Private B work/);assert.doesNotMatch(switched,/Fix A tests/);
});
test('Projects sidebar has recovery and empty states',()=>{
 assert.match(renderToStaticMarkup(React.createElement(ProjectsSidebar,{...props,projects:[],conversations:[]})),/Connect a repository/);
 const html=renderToStaticMarkup(React.createElement(ProjectsSidebar,{...props,busy:true,error:'Backend unavailable'}));
 assert.match(html,/role="alert"/);assert.match(html,/Retry/);assert.match(html,/disabled/);
});
test('release dashboard renders disabled Live without mounting the provider control',()=>{
 const noop=()=>null;
 const {DashboardView}=load('../components/DashboardView.tsx',{
 '../hooks/useTaskEventStream':{useTaskEventStream:()=>({events:[],isConnected:false,error:null})},
 './EngineeringStream':{EngineeringStream:noop},'./ModelSelector':{ModelSelector:noop},
 './ProjectsSidebar':{ProjectsSidebar},'../lib/engineering-stream':load('../lib/engineering-stream.ts'),
 '../lib/composer':load('../lib/composer.ts'),
 });
 const html=renderToStaticMarkup(React.createElement(DashboardView,{client:{},preferences:{theme:'light'},tasks:[],agents:[],currentUser:{role:'DEVELOPER'},onRefresh(){}}));
 assert.match(html,/<button[^>]*disabled[^>]*aria-label="Live temporarily unavailable"/);
 assert.doesNotMatch(html,/Start Live Voice/);assert.match(html,/aria-label="Voice Input"/);
});
