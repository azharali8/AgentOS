"use client";
import {useCallback,useEffect,useState} from 'react';
import {AgentOSClient,LocalModels} from '../lib/api';
import {Theme,resolvedTheme,savedTheme} from '../lib/theme';
export function useWorkspaceSettings(client:AgentOSClient,authenticated:boolean) {
 const [theme,setThemeState]=useState<Theme>('light');
 const [readAloud,setReadAloudState]=useState(true);
 const [models,setModels]=useState<LocalModels|null>(null);
 const [error,setError]=useState(''); const [busy,setBusy]=useState(false);
 useEffect(()=>{setThemeState(savedTheme(localStorage.getItem('agentos_theme')));setReadAloudState(localStorage.getItem('agentos_read_aloud')!=='false');},[]);
 useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const apply=()=>{document.documentElement.dataset.theme=resolvedTheme(theme,media.matches);};apply();media.addEventListener('change',apply);return()=>media.removeEventListener('change',apply);},[theme]);
 const setTheme=(value:Theme)=>{localStorage.setItem('agentos_theme',value);setThemeState(value);};
 const setReadAloud=(value:boolean)=>{localStorage.setItem('agentos_read_aloud',String(value));setReadAloudState(value);};
 const refresh=useCallback(async()=>{if(!authenticated)return;setBusy(true);try{setModels(await client.localModels());setError('');}catch{setModels(null);setError('Unable to reach model settings. Check the backend connection.');}finally{setBusy(false);}},[client,authenticated]);
 useEffect(()=>{void refresh();},[refresh]);
 const select=async(model:string)=>{setBusy(true);try{setModels(await client.selectLocalModel(model));setError('');}catch{setError('Model selection failed. Check Ollama and refresh available models.');}finally{setBusy(false);}};
 return {theme,setTheme,readAloud,setReadAloud,models,error,busy,refresh,select};
}
export type WorkspaceSettings = ReturnType<typeof useWorkspaceSettings>;
