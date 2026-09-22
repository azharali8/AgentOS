"use client";
import {useEffect,useRef,useState} from 'react';
import {WorkspaceSettings} from '../hooks/useWorkspaceSettings';
import {modelLabel} from '../lib/model-label';

export function ModelSelector({preferences,disabled=false}:{preferences:WorkspaceSettings;disabled?:boolean}) {
 const {models,busy,select,refresh}=preferences;
 const [open,setOpen]=useState(false);
 const root=useRef<HTMLDivElement>(null);
 const trigger=useRef<HTMLButtonElement>(null);
 const list=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  if(!open)return;
  const close=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))setOpen(false);};
  document.addEventListener('pointerdown',close);
  list.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]:not(:disabled),button:not(:disabled)')?.focus();
  return()=>document.removeEventListener('pointerdown',close);
 },[open]);
 useEffect(()=>{if(disabled)setOpen(false);},[disabled]);
 const close=()=>{setOpen(false);trigger.current?.focus();};
 return <div ref={root} className="model-picker" onKeyDown={event=>{
  if(event.key==='Escape'){event.preventDefault();close();}
  if(event.key==='Tab')setOpen(false);
  if(open&&['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
   event.preventDefault();
   const items=Array.from(list.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')??[]);
   const index=items.indexOf(document.activeElement as HTMLButtonElement);
   const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;
   items[next]?.focus();
  }
 }}>
  <button ref={trigger} type="button" className="model-select" aria-label="Active local AI model" aria-haspopup="listbox" aria-expanded={open} disabled={disabled} onClick={()=>setOpen(!open)} onKeyDown={event=>{if(!open&&['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();setOpen(true);}}}>
   <span>{models?modelLabel(models.active_model):busy?'Loading models…':'Choose model'}</span><span aria-hidden="true">⌄</span>
  </button>
  {open&&<div className="model-menu">
   {busy&&<p role="status">Checking models…</p>}
   {models&&!models.selection_enabled&&<p>Model selection requires the Ollama provider.</p>}
   {models?.status==='offline'&&<p role="alert">Ollama is offline.</p>}
   {preferences.error&&<p role="alert">{preferences.error}</p>}
   <div ref={list} role="listbox" aria-label="Available AI models">
    {models?.models.filter(m => m.selectable).map(model=><button type="button" role="option" key={model.name} aria-selected={model.name===models.active_model} disabled={busy||!models.selection_enabled||models.status!=='online'} onClick={()=>{close();void select(model.name);}}>
     <span>{modelLabel(model.name)}</span><small>{model.cloud?'Cloud':'Local'}</small>
    </button>)}
   </div>
   {!busy&&!models?.models.filter(m => m.selectable).length&&<p>No compatible chat models found.</p>}
   <button type="button" className="model-refresh" disabled={busy} onClick={()=>void refresh()}>Refresh models</button>
  </div>}
 </div>;
}
