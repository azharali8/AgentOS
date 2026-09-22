const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function load(file,requires={}){
 const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText,{exports,require:name=>requires[name]??require(name)});return exports;
}
const policy=load('../lib/registration-password.ts');
test('registration requires 8 to 20 characters and special punctuation',()=>{
 for(const [password,valid] of [['a'.repeat(6)+'!',false],['a'.repeat(7)+'!',true],['a'.repeat(8),false],['a'.repeat(19)+'!',true],['a'.repeat(20)+'!',false],['🙂'.repeat(19)+'!',true],['a'.repeat(7)+' ',false],['space phrase!',true]]) assert.equal(policy.registrationPasswordError(password)==='',valid);
});
async function screen(enabled){
 const states=[],effects=[];let cursor=0,mounted=false,calls=0;
 const react={...React,useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return [states[i],value=>states[i]=value];},useEffect:fn=>{if(!mounted)effects.push(fn);}};
 const component=load('../components/auth/LoginView.tsx',{'react':react,'lucide-react':new Proxy({}, {get:()=>()=>null}),'next/link':({children,...props})=>React.createElement('a',props,children),'../../lib/api':{AgentOSClient:class{async authOptions(){calls++;return {registration_enabled:enabled};}}},'../../lib/auth-session':{authError:()=>''},'../../lib/registration-password':policy}).LoginView;
 const render=()=>{cursor=0;return component({onLoginSuccess:()=>{}});};
 render();mounted=true;effects.forEach(fn=>fn());await Promise.resolve();await Promise.resolve();
 return {render,calls:()=>calls};
}
function find(node,predicate){if(!node||typeof node!=='object')return null;if(predicate(node))return node;for(const child of React.Children.toArray(node.props?.children)){const result=find(child,predicate);if(result)return result;}return null;}
for(const enabled of [false,true])test(`backend registration_enabled=${enabled} controls Create account`,async()=>{
 const s=await screen(enabled);assert.equal(s.calls(),1);const tree=s.render();assert.equal(renderToStaticMarkup(tree).includes('Create account'),enabled);
 if(enabled){find(tree,n=>n.type==='button'&&n.props.children==='Create account').props.onClick();const signup=s.render();assert.ok(renderToStaticMarkup(signup).includes('Password requirements'));const password=find(signup,n=>n.props.id==='auth-password');assert.equal(password.props.placeholder,'Create a password');assert.equal(password.props.maxLength,undefined);}
});

test('password guidance updates while typing and invalid passwords do not submit',async()=>{
 const s=await screen(true);find(s.render(),n=>n.type==='button'&&n.props.children==='Create account').props.onClick();
 for(const [value,message] of [['abc','Add 5 more characters'],['abcdefgh','Add a special character'],['abcdefgh!','Your password meets the requirements.'],['a'.repeat(20)+'!','Use no more than 20 characters.']]){
  find(s.render(),n=>n.props.id==='auth-password').props.onChange({target:{value}});
  assert.ok(renderToStaticMarkup(s.render()).includes(message));
 }
 await find(s.render(),n=>n.type==='form').props.onSubmit({preventDefault(){}});
 assert.ok(renderToStaticMarkup(s.render()).includes(policy.REGISTRATION_PASSWORD_MESSAGE));
});
