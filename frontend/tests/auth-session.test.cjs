const {test}=require('node:test');
const assert=require('node:assert/strict');
const ts=require('typescript');
const fs=require('node:fs');
const vm=require('node:vm');
const exportsUnderTest={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(require('node:path').join(__dirname,'../lib/auth-session.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{exports:exportsUnderTest});
const {restoreSession,authError}=exportsUnderTest;
function storage(){const map=new Map([['agentos_token','session'],['agentos_user',JSON.stringify({role:'ADMIN'})]]);return {map,getItem:key=>map.get(key),removeItem:key=>map.delete(key)};}
const profile={user_id:'u1',username:'Engineer',role:'user',is_authenticated:true};
test('reload resolves identity on server and discards cached role claims',async()=>{const s=storage();let received;const result=await restoreSession(s,async token=>{received=token;return profile;});assert.equal(received,'session');assert.equal(result.user.role,'USER');assert.equal(s.map.has('agentos_user'),false);});
test('expired and rejected sessions remove credentials',async()=>{for(const status of [401,403]){const s=storage();await assert.rejects(restoreSession(s,async()=>{throw {status};}));assert.equal(s.map.has('agentos_token'),false);}});
test('connection failure keeps retry token but cannot open workspace',async()=>{const s=storage();await assert.rejects(restoreSession(s,async()=>{throw new Error('offline');}));assert.equal(s.map.get('agentos_token'),'session');});
test('invalid authenticated profile cannot open workspace',async()=>{for(const changes of [{role:'ROOT'},{is_authenticated:false},{user_id:''}])await assert.rejects(restoreSession(storage(),async()=>({...profile,...changes})));});
test('missing session does not contact profile API',async()=>{const s=storage();s.map.clear();assert.equal(await restoreSession(s,()=>{throw Error('unexpected');}),null);});
test('authentication messages never expose raw server secrets or markup',()=>{for(const status of [400,401,403,404,422,429,500,undefined]){const message=authError({status,message:'<script>secret-token</script>'});assert.ok(message.length>10);assert.equal(message.includes('secret-token'),false);assert.equal(message.includes('<script>'),false);}});
