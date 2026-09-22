"use client";
import {useEffect,useRef,useState} from 'react';
import {Plus,ArrowUp,X,Loader2} from 'lucide-react';
import {supervisorStage} from '../lib/voice-stream';
import {AgentOSClient} from '../lib/api';
import {WorkspaceSettings} from '../hooks/useWorkspaceSettings';
import {ModelSelector} from './SettingsView';
import {VoiceControl} from './voice/VoiceControl';
import {Attachment,ACCEPTED_CONTEXT,readAttachment,shouldSubmit} from '../lib/composer';
export function CommandComposer({client,preferences,onTaskCreated,disabled=false}:{client:AgentOSClient;preferences:WorkspaceSettings;onTaskCreated:(id:string)=>void;disabled?:boolean}) {
 const [text,setText]=useState(''),[attachments,setAttachments]=useState<Attachment[]>([]),[busy,setBusy]=useState(false),[attaching,setAttaching]=useState(false),[error,setError]=useState(''),[voice,setVoice]=useState(false);
 const [taskId,setTaskId]=useState<string|null>(null),[stage,setStage]=useState('');
 const created=(id:string)=>{setTaskId(id);onTaskCreated(id);};
 useEffect(()=>{if(!taskId)return;let active=true;let polling=false;const update=async()=>{if(polling)return;polling=true;try{const [task,events]=await Promise.all([client.getTask(taskId),client.getTaskEvents(taskId)]);if(active)setStage(supervisorStage(task.status,events));}catch{if(active)setStage('Progress unavailable. Check task activity.');}finally{polling=false;}};void update();const timer=setInterval(update,4000);return()=>{active=false;clearInterval(timer);};},[taskId,client]);
 const input=useRef<HTMLInputElement>(null);const sending=useRef(false);
 const submit=async()=>{if(!text.trim()||sending.current||voice||disabled||attaching)return;sending.current=true;setBusy(true);setError('');try{const task=await client.createTask(text.trim(),1,{attachments});setText('');setAttachments([]);created(task.task_id);}catch{setError('Could not submit this request. Check the backend, model availability, and attached files.');}finally{sending.current=false;setBusy(false);}};
 return <div className="command-composer">
 <div className="attachment-chips">{attachments.map((a,i)=><span key={i}>{a.name}<button aria-label={'Remove '+a.name} disabled={busy||voice} onClick={()=>setAttachments(attachments.filter((_,j)=>j!==i))}><X size={14}/></button></span>)}</div>
 <textarea aria-label="Instruction for AgentOS" placeholder="Ask AgentOS to build, fix, test, or review..." value={text} disabled={busy||voice||disabled} rows={2} onChange={e=>{setText(e.target.value);e.target.style.height='auto';e.target.style.height=Math.min(220,e.target.scrollHeight)+'px';}} onKeyDown={e=>{if(shouldSubmit(e.key,e.shiftKey,e.nativeEvent.isComposing)){e.preventDefault();void submit();}}}/>
 <div className="composer-toolbar"><input ref={input} hidden type="file" accept={ACCEPTED_CONTEXT} multiple onChange={async e=>{const files=Array.from(e.target.files??[]);e.target.value='';setAttaching(true);setError('');try{const added=await Promise.all(files.map(readAttachment));const next=[...attachments,...added];if(next.length>4||next.reduce((n,a)=>n+new TextEncoder().encode(a.content).length,0)>65536)throw Error('Use at most four files totaling 64 KB.');setAttachments(next);}catch(err){setError(err instanceof Error?err.message:'Attachment rejected.');}finally{setAttaching(false);}}}/>
 <button type="button" className="composer-icon" aria-label="Attach text or source files" title="Attach text or source files (32 KB each)" disabled={busy||attaching||voice||disabled} onClick={()=>input.current?.click()}>{attaching?<Loader2 size={19}/>:<Plus size={20}/>}</button>
 <div className="composer-actions"><ModelSelector preferences={preferences} disabled={busy||voice||disabled}/><button className="composer-send" aria-label="Send to Supervisor" disabled={!text.trim()||busy||voice||attaching||disabled} onClick={()=>void submit()}>{busy?<Loader2 size={19} className="animate-spin"/>:<ArrowUp size={19}/>}</button><VoiceControl client={client} onTaskCreated={created} readAloud={preferences.readAloud} onActiveChange={setVoice} disabled={busy||attaching||disabled||attachments.length>0||!!text.trim()}/></div></div>
 {stage&&<p className="composer-progress" role="status">Supervisor · {stage}</p>}
 {(error||preferences.error)&&<p className="composer-error" role="alert">{error||preferences.error}</p>}
 {attachments.length>0&&<p className="composer-hint">Attached files are context for this typed request. Remove them to start voice.</p>}
 </div>;
}
