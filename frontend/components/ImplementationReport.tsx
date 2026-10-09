'use client';
import React, {useEffect, useState} from 'react';
import {AgentOSClient, ImplementationReport as Report} from '../lib/api';
import {safeDisplay} from '../lib/engineering-stream';

export function ImplementationReportView({report,onOpenArtifact}:{report:Report;onOpenArtifact?:(id:string)=>void}) {
  const link=(id:string,label:string)=><button type="button" className="engineering-link" onClick={()=>onOpenArtifact?.(id)}>{label}</button>;
  return <section className="border-t theme-border mt-8 pt-6 space-y-4 text-sm" aria-label="Session implementation report" data-report-id={report.report_id}>
    <header><h3 className="font-semibold">Session implementation report</h3><p className="text-xs theme-text-muted mt-1">{report.status.replaceAll('_',' ')} · task {report.task_id.slice(0,8)}</p></header>
    <p>{safeDisplay(report.summary)}</p>
    {report.changes.length>0&&<div><h4 className="font-medium">Changes made</h4><ul className="mt-2 space-y-1">{report.changes.map((change,i)=><li key={i}><strong>{change.category}:</strong> {safeDisplay(change.description)}</li>)}</ul></div>}
    <div><h4 className="font-medium">Files changed · {report.files_changed.length}</h4>{report.files_changed.length===0?<p className="theme-text-muted text-xs">No applied file changes recorded.</p>:<ul className="mt-2 space-y-2">{report.files_changed.map(file=><li key={file.path}><code>{safeDisplay(file.path)}</code>{file.additions!==null&&file.deletions!==null&&<span className="ml-3 text-xs">+{file.additions} −{file.deletions} (applied patch lines)</span>}<div className="flex gap-3 text-xs">{file.diffs.map((id,i)=><span key={id}>{link(id,`View diff${file.diffs.length>1?` ${i+1}`:''}`)}</span>)}</div></li>)}</ul>}</div>
    {report.commands.length>0&&<details><summary>Commands executed · {report.commands.length}</summary><ul className="mt-2 space-y-2">{report.commands.map((command,i)=><li key={`${command.artifact_id}:${i}`}><code>{safeDisplay(command.command)}</code><p>{command.status} · exit {command.exit_code??'unknown'}</p></li>)}</ul></details>}
    {report.tools.length>0&&<details><summary>Recorded tools · {report.tools.length}</summary><ul>{report.tools.map(tool=><li key={tool.execution_id}>{safeDisplay(tool.tool)} · {safeDisplay(tool.operation)} · {tool.status}</li>)}</ul></details>}
    <div><h4 className="font-medium">Tests and verification</h4>{report.tests.length===0?<p className="theme-text-muted text-xs">No test results recorded.</p>:<ul className="mt-2 space-y-2">{report.tests.map((test,i)=><li key={test.artifact_id}>{link(test.artifact_id,`Test run ${i+1}`)} · {test.passed?'PASSED':'FAILED / UNVERIFIED'}<p className="text-xs">{test.passed_count??'?'} passed · {test.failed_count??'?'} failed{test.skipped_count!==null?` · ${test.skipped_count} skipped`:''} · exit {test.exit_code??'unknown'}</p></li>)}</ul>}</div>
    <div><h4 className="font-medium">Approvals</h4>{report.approvals.length?<ul>{report.approvals.map(approval=><li key={approval.approval_id}>{approval.approval_id.slice(0,8)} · {approval.status}</li>)}</ul>:<p className="theme-text-muted text-xs">No approval records. This does not establish that approval was required or bypassed.</p>}</div>
    {report.reviews.length>0&&<div><h4 className="font-medium">Review</h4>{report.reviews.map(review=><p key={review.artifact_id}>{link(review.artifact_id,review.status.replaceAll('_',' '))}{review.summary&&` · ${safeDisplay(review.summary)}`}</p>)}</div>}
    {report.artifacts.length>0&&<div><h4 className="font-medium">Artifacts</h4><div className="flex flex-wrap gap-3 mt-2 text-xs">{report.artifacts.map(artifact=><span key={artifact.artifact_id}>{link(artifact.artifact_id,`${artifact.label} · ${artifact.artifact_id.slice(0,8)}`)}</span>)}</div></div>}
    {report.warnings.map((warning,i)=><p key={i} className="theme-text-muted text-xs">{safeDisplay(warning)}</p>)}
    <div><h4 className="font-medium">Remaining issues</h4>{report.remaining_issues.length?<ul className="list-disc pl-5">{report.remaining_issues.map((issue,i)=><li key={i}>{safeDisplay(issue)}</li>)}</ul>:<p className="theme-text-muted text-xs">No unresolved issues identified in the recorded evidence. Unrecorded verification is not implied.</p>}</div>
  </section>;
}

export function SessionImplementationReport({client,taskId,revision}:{client:AgentOSClient;taskId:string;revision:string}) {
  const [report,setReport]=useState<Report|null>(null),[error,setError]=useState(false),[retry,setRetry]=useState(0);
  const [artifactId,setArtifactId]=useState<string|null>(null),[artifact,setArtifact]=useState<string|null>(null),[artifactError,setArtifactError]=useState(false);
  useEffect(()=>{setArtifactId(null);},[taskId]);
  useEffect(()=>{let disposed=false;setArtifact(null);setArtifactError(false);if(artifactId)client.getArtifact(artifactId).then(value=>{if(!disposed){if(value.task_id!==taskId)throw new Error('Artifact scope mismatch');setArtifact(safeDisplay(JSON.stringify(value.content,(key,item)=>/reasoning|chain.of.thought/i.test(key)?undefined:item,2)));}}).catch(()=>{if(!disposed)setArtifactError(true);});return()=>{disposed=true;};},[client,taskId,artifactId]);
  useEffect(()=>{let disposed=false;setReport(null);setError(false);client.getImplementationReport(taskId).then(value=>{if(!disposed&&value.task_id===taskId)setReport(value);}).catch(()=>{if(!disposed)setError(true);});return()=>{disposed=true;};},[client,taskId,revision,retry]);
  if(error)return <p role="alert" className="mt-6 text-sm">Implementation report unavailable. <button className="engineering-link" onClick={()=>setRetry(value=>value+1)}>Retry report</button></p>;
  if(!report||report.task_id!==taskId)return <p role="status" className="mt-6 text-xs theme-text-muted">Loading recorded implementation report…</p>;
  return <><ImplementationReportView report={report} onOpenArtifact={setArtifactId}/>{artifactId&&<section className="mt-4 text-xs" aria-label="Recorded artifact"><div className="flex justify-between"><strong>Recorded artifact · {artifactId.slice(0,8)}</strong><button className="engineering-link" onClick={()=>setArtifactId(null)}>Close artifact</button></div>{artifactError?<p role="alert">Artifact unavailable. Close and reopen to retry.</p>:artifact===null?<p role="status">Loading artifact…</p>:<pre className="engineering-code mt-2 max-h-96 overflow-auto">{artifact}</pre>}</section>}</>;
}
