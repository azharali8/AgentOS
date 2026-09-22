'use client';
import React,{useMemo,useState} from 'react';
import {Check,Loader2,X,FileText,Terminal,Code2,ShieldCheck,Bug,Paperclip} from 'lucide-react';
import {Task,TaskEvent,ApprovalRequestItem} from '../types';
import {AgentOSClient} from '../lib/api';
import {Artifact,EngineeringEntry,engineeringEntries,patchFiles,safeDisplay,taskIsTerminal} from '../lib/engineering-stream';

function PatchPreview({data}:{data:Record<string,any>}){
 const files=patchFiles(data);
 if(!files.length)return <p className="theme-text-muted text-xs">Loading patch evidence…</p>;
 return <div className="engineering-patch">{files.map(f=><div key={f.path} className="my-3">
  <div className="flex justify-between gap-3 text-xs"><strong>{f.path}</strong><span className="font-mono"><span className="text-emerald-700">+{f.added}</span> <span className="text-rose-700">−{f.removed}</span></span></div>
  <pre className="engineering-code mt-2" aria-label={`Patch preview ${f.path}`}>{f.lines.filter(l=>/^[+-]/.test(l)).slice(0,8).map((l,i)=><span className={l.startsWith('+')?'text-emerald-700':'text-rose-700'} key={i}>{l.endsWith('\n')?l:l+'\n'}</span>)}</pre>
  <details><summary>View full diff · {f.path}</summary><pre className="engineering-code">{f.lines.join('')}</pre></details>
 </div>)}</div>;
}
function TestEvidence({data}:{data:Record<string,any>}){
 const command=Array.isArray(data.command)?data.command.join(' '):data.command;
 const output=data.stdout_redacted||data.raw_stdout||'';const errors=data.stderr_redacted||data.raw_stderr||'';
 return <div className="space-y-2 text-xs">
  {command&&<code className="block theme-text-muted">&gt; {safeDisplay(command)}</code>}
  <p>{typeof data.passed_count==='number'&&`${data.passed_count} passed`}{typeof data.failed_count==='number'&&` · ${data.failed_count} failed`}{typeof data.duration_seconds==='number'&&` · ${data.duration_seconds.toFixed(1)}s`}{typeof data.exit_code==='number'&&` · exit ${data.exit_code}`}</p>
  {(data.issues||[]).map((issue:any,i:number)=><div key={i} className="border-l-2 border-rose-300 pl-3"><strong>{safeDisplay(issue.title)}</strong><p>{safeDisplay(issue.test_file||issue.source_file)}{issue.line?`:${issue.line}`:''}</p><p className="whitespace-pre-wrap">{safeDisplay(issue.error_message||issue.error||issue.summary)}</p></div>)}
  {(output||errors)&&<details><summary>View terminal output</summary><pre className="engineering-code">{safeDisplay(output)}{'\n'}{safeDisplay(errors)}</pre></details>}
 </div>;
}
function EntryDetails({row}:{row:EngineeringEntry}){
 if(row.kind==='patch')return <PatchPreview data={row.data||{}}/>;
 if(row.kind==='test')return <TestEvidence data={row.data||{}}/>;
 return <>{row.detail&&<p className="text-sm whitespace-pre-wrap break-words">{row.detail}</p>}{row.kind==='diagnosis'&&row.data?.suggested_fix&&<p className="text-xs">Suggested fix: {safeDisplay(row.data.suggested_fix)}</p>}{row.kind==='review'&&Array.isArray(row.data?.recommendations)&&<ul className="text-xs list-disc pl-4">{row.data!.recommendations.map((r:any,i:number)=><li key={i}>{safeDisplay(r)}</li>)}</ul>}</>;
}
export function EngineeringStream({task,events,artifacts,approval,isStreaming,streamError,client,userRole,onResolved,onViewFile}:{task:Task;events:TaskEvent[];artifacts:Artifact[];approval:ApprovalRequestItem|null;isStreaming:boolean;streamError?:string|null;client:AgentOSClient;userRole?:string;onResolved:()=>void;onViewFile:(path:string)=>void}){
 const entries=useMemo(()=>engineeringEntries(task,events,artifacts),[task,events,artifacts]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[resolved,setResolved]=useState<string|null>(null);
 const pending=approval?.task_id===task.task_id&&approval.status==='PENDING'&&approval.approval_id!==resolved?approval:null;
 const canApprove=['DEVELOPER','ADMIN'].includes(userRole||'');
 const resolve=async(approved:boolean)=>{if(!pending||busy||!canApprove)return;setBusy(true);setError('');try{await client.resolveApproval(pending.approval_id,approved);setResolved(pending.approval_id);onResolved();}catch{setError('Approval could not be resolved. Check your permissions or refresh this task before retrying.');}finally{setBusy(false);}};
 const approvalBlock=(id:string)=><section key={id} className="engineering-approval" aria-label="Changes ready for review"><h3>Changes ready for review</h3><p className="text-xs theme-text-muted">AgentOS needs permission to apply these changes.</p><p className="text-xs font-mono my-2">{(pending?.arguments_summary?.files||[]).join(', ')}</p><p className="text-xs">Inspect the proposed diff above before applying.</p>{!canApprove&&<p className="text-xs my-2">A Developer or Admin must approve these changes.</p>}<div className="flex gap-2 mt-3"><button disabled={busy||!canApprove} onClick={()=>void resolve(false)}>Reject</button><button className="engineering-approve" disabled={busy||!canApprove} onClick={()=>void resolve(true)}>{busy?'Applying decision…':'Approve & Apply'}</button></div>{error&&<p role="alert" className="text-rose-700 text-xs mt-2">{error}</p>}</section>;
 const hasApprovalRow=entries.some(e=>e.kind==='approval'&&e.data?.approval_id===pending?.approval_id);
 const changed=Array.from(new Set(events.filter(e=>e.event_type==='PATCH_APPLIED'&&e.payload?.applied===true).flatMap(e=>e.payload?.files||e.payload?.modified_files||[]))) as string[];
 return <div className="engineering-stream select-text" aria-label="Engineering conversation">
  <header className="flex items-baseline gap-2 mb-5"><strong className="text-sm">AgentOS</strong><span className="text-[11px] theme-text-muted">Supervisor · {isStreaming?'Live':'Connecting to activity'}</span></header>
  {streamError&&<p className="text-xs text-amber-700" role="status">Live updates interrupted. Reconnecting; task status is not confirmed.</p>}
  {entries.length===0&&!taskIsTerminal(task.status)&&<p className="engineering-row"><Loader2 className="engineering-active" size={14}/> Request submitted. Waiting for Supervisor activity…</p>}
  <ol className="space-y-3" aria-live="polite" aria-relevant="additions text">{entries.map(row=>{
   if(row.kind==='approval'&&pending?.approval_id===row.data?.approval_id)return <li key={row.id}>{approvalBlock(row.id)}</li>;
   const Icon=row.state==='active'?Loader2:row.state==='failed'?X:row.kind==='file'?FileText:row.kind==='patch'?Code2:row.kind==='test'?Terminal:row.kind==='review'?ShieldCheck:row.kind==='diagnosis'?Bug:Check;
   const rich=['patch','test','diagnosis','review'].includes(row.kind);
   return <li key={row.id} className={`engineering-entry ${row.state==='failed'?'engineering-failed':''}`} data-state={row.state}>
    <div className="engineering-row"><Icon size={14} className={row.state==='active'?'engineering-active':''}/><span>{row.title}</span>{row.kind==='file'&&<button className="engineering-link" onClick={()=>onViewFile(row.data?.path)}>View</button>}</div>
    {row.agent&&<p className="engineering-meta">{row.agent} agent · delegated by Supervisor</p>}
    {row.kind==='patch'?(taskIsTerminal(task.status)||entries.filter(e=>e.kind==='patch').slice(-1)[0]?.id!==row.id?<details className="engineering-details"><summary>View proposed diff</summary><EntryDetails row={row}/></details>:<EntryDetails row={row}/>):rich||row.detail?<details key={`${row.id}:${row.state}`} open={row.state==='active'||row.kind==='final'||row.state==='failed'} className="engineering-details"><summary>{row.kind==='final'?'Result':row.kind==='test'?'Test evidence':'View details'}</summary><EntryDetails row={row}/></details>:null}
    {row.artifact&&<span className="engineering-artifact"><Paperclip size={11}/>{row.artifact.artifact_type.replaceAll('_',' ')} · {row.artifact.artifact_id.slice(0,8)}</span>}
   </li>;
  })}</ol>
  {pending&&!hasApprovalRow&&approvalBlock(pending.approval_id)}
  {resolved&&!taskIsTerminal(task.status)&&<p className="text-xs theme-text-muted mt-3" role="status">Decision submitted. Waiting for the next execution event…</p>}
  {taskIsTerminal(task.status)&&changed.length>0&&<div className="mt-4 text-xs"><strong>Changed files</strong><ul className="mt-2 space-y-1">{changed.map(f=><li key={f}>{f}</li>)}</ul></div>}
 </div>;
}
