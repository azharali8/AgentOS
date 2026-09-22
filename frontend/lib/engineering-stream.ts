import {Task, TaskEvent} from '../types';
export type Artifact = {artifact_id:string; task_id:string; artifact_type:string; created_at:string; content:Record<string,any>};
export type EngineeringEntry = {id:string; time:string; kind:string; title:string; state:'active'|'done'|'failed'|'waiting'; agent?:string; detail?:string; data?:Record<string,any>; artifact?:Artifact};
const running:Record<string,string>={coding:'Preparing changes',testing:'Running tests',debugger:'Investigating failure',reviewer:'Reviewing changes',research:'Inspecting project',security:'Checking security',documentation:'Updating documentation'};
const finished:Record<string,string>={coding:'Changes proposed',testing:'Test execution finished',debugger:'Investigation finished',reviewer:'Review finished',research:'Project inspection finished',security:'Security check finished',documentation:'Documentation prepared'};
const failed:Record<string,string>={coding:'Implementation stopped',testing:'Test execution failed',debugger:'Investigation failed',reviewer:'Review failed',research:'Project inspection failed',security:'Security check failed',documentation:'Documentation failed'};
export const taskIsTerminal=(status:string)=>['COMPLETED','FAILED','CANCELLED'].includes(status);
export const shouldFollowStream=(top:number,height:number,viewport:number)=>height-top-viewport<100;
export function safeDisplay(value:unknown):string {
 if(typeof value!=='string')return '';
 return value.replace(/(?:Bearer\s+)[\w.\-]+/gi,'Bearer [redacted]').replace(/((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+/gi,'$1[redacted]').replace(/[A-Z]:[\\/](?:[^\s'"<>]+[\\/])*[^\s'"<>]*/gi,'[local path]').slice(0,16000);
}
export function patchFiles(content:Record<string,any>) {
 return (Array.isArray(content.files)?content.files:[]).map((file:any)=>{
  const lines:string[]=(file.hunks||[]).flatMap((h:any)=>h.lines||[]).filter((l:any)=>typeof l==='string');
  return {path:String(file.relative_path||''),lines,added:lines.filter(l=>l.startsWith('+')).length,removed:lines.filter(l=>l.startsWith('-')).length};
 });
}
export function engineeringEntries(task:Task,events:TaskEvent[],artifacts:Artifact[]):EngineeringEntry[]{
 const rows:EngineeringEntry[]=[];const keys=new Map<string,EngineeringEntry>();const ids=new Set<string>();
 const add=(row:EngineeringEntry)=>{if(keys.has(row.id))return keys.get(row.id)!;keys.set(row.id,row);rows.push(row);return row;};
 const ordered=events.filter(e=>e.task_id===task.task_id).map((e,i)=>({e,i})).sort((a,b)=>Date.parse(a.e.timestamp)-Date.parse(b.e.timestamp)||a.i-b.i);
 for(const {e} of ordered){
  if(ids.has(e.event_id))continue;ids.add(e.event_id);
  const p=e.payload||{};const type=e.event_type;const base={time:e.timestamp,state:'done' as const};
  if(type==='TASK_CREATED')add({...base,id:'received',kind:'action',title:'Request received'});
  else if(type==='PLAN_CREATED')add({...base,id:'plan',kind:'action',title:'Planning work',state:events.some(x=>x.event_type==='SUBTASK_CREATED')?'done':'active'});
  else if(type==='MODEL_SELECTED')add({...base,id:'model',kind:'metadata',title:`Model: ${safeDisplay(p.model)}`});
  else if(type==='FILE_READ')add({...base,id:`read:${p.subtask_id||p.agent||''}:${p.path}`,kind:'file',title:`Read ${safeDisplay(p.path)}`,data:{path:p.path}});
  else if(type==='SUBTASK_STARTED'||type==='SUBTASK_COMPLETED'||type==='SUBTASK_FAILED'){
   const agent=String(p.agent||p.agent_type||'agent').toLowerCase();const id=`subtask:${p.subtask_id||e.step_id||e.event_id}`;
   const row=add({...base,id,kind:agent==='debugger'?'diagnosis':'action',title:running[agent]||'Executing delegated work',state:'active',agent});
   if(type!=='SUBTASK_STARTED'){row.state=type==='SUBTASK_FAILED'||['failed','timeout','cancelled'].includes(p.status)?'failed':'done';row.title=row.state==='failed'?failed[agent]||'Subtask failed':finished[agent]||'Work finished';row.detail=safeDisplay(p.error||p.summary);}
  }
  else if(type==='PATCH_CREATED')add({...base,id:`patch:${p.patch_id||e.event_id}`,kind:'patch',title:'Proposed changes',data:{patch_id:p.patch_id,files:p.files}});
  else if(type==='PATCH_APPLIED')add({...base,id:`applied:${p.patch_id||p.patch_hash||e.event_id}`,kind:'action',title:p.applied===false?'Patch application failed':'Changes applied',state:p.applied===false?'failed':'done',detail:(p.files||p.modified_files||[]).join(', ')});
  else if(type==='TEST_COMPLETED')add({...base,id:`test:${e.event_id}`,kind:'test',title:p.report?.passed===true?'Tests passed':'Test results',state:p.report?.passed===false?'failed':'done',data:p.report||{}});
  else if(['DEBUG_DIAGNOSIS_CREATED','REPLAN_TRIGGERED'].includes(type))add({...base,id:e.event_id,kind:'diagnosis',title:type==='REPLAN_TRIGGERED'?'Replanning after failure':'Diagnosis available',detail:safeDisplay(p.summary||p.reason),data:p.diagnosis});
  else if(['APPROVAL_REQUIRED','APPROVAL_REQUESTED'].includes(type))add({...base,id:`approval:${p.approval_id}`,kind:'approval',title:'Changes ready for review',state:'waiting',data:p});
  else if(type==='APPROVAL_RESOLVED'){
   const previous=keys.get(`approval:${p.approval_id}`);if(previous){previous.state='done';previous.title='Approval resolved';}
   add({...base,id:e.event_id,kind:'action',title:p.approved===false||p.decision==='REJECTED'?'Changes rejected':'Approval resolved'});
  }
 }
 for(const art of artifacts.filter(a=>a.task_id===task.task_id)){
  const c=art.content||{};
  if(art.artifact_type==='PATCH'){
   const row=keys.get(`patch:${c.patch_id}`)||add({id:`patch:${c.patch_id||art.artifact_id}`,time:art.created_at,kind:'patch',title:'Proposed changes',state:'done'});row.artifact=art;row.data=c;
  }else if(art.artifact_type==='TEST_REPORT'){
   const candidate=rows.filter(r=>r.kind==='test'&&!r.artifact).find(r=>Math.abs(Date.parse(r.time)-Date.parse(art.created_at))<10000);
   const row=candidate||add({id:`artifact:${art.artifact_id}`,time:art.created_at,kind:'test',title:c.passed===true?'Tests passed':'Test results',state:c.passed===false?'failed':'done'});row.artifact=art;row.data={...c,...row.data};
  }else if(['REVIEW','DIAGNOSIS'].includes(art.artifact_type))add({id:`artifact:${art.artifact_id}`,time:art.created_at,kind:art.artifact_type.toLowerCase(),title:art.artifact_type==='REVIEW'?(c.approved?'Review approved':'Review findings'):'Diagnosis',state:c.approved===false?'failed':'done',detail:safeDisplay(c.summary||c.root_cause),artifact:art,data:c});
 }
 const stopped=taskIsTerminal(task.status)||task.status==='WAITING_APPROVAL';
 if(stopped)for(const r of rows)if(r.state==='active'){r.state=task.status==='FAILED'?'failed':'done';}
 if(taskIsTerminal(task.status))add({id:'final',time:task.completed_at||task.updated_at||ordered[ordered.length-1]?.e.timestamp||task.created_at,kind:'final',title:task.status==='COMPLETED'?'Work completed':task.status==='FAILED'?'Execution stopped':'Task cancelled',state:task.status==='COMPLETED'?'done':'failed',detail:safeDisplay(task.error||task.result_summary)});
 return rows.sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
}
