'use client';
import {useCallback, useEffect, useRef, useState} from 'react';
import {AgentOSClient} from '../lib/api';
import {restoreSession, verifiedProfile} from '../lib/auth-session';
import {UserProfile} from '../types';
export function useAuthSession() {
  const [token,setToken]=useState<string|null>(null);
  const [user,setUser]=useState<UserProfile|null>(null);
  const [checking,setChecking]=useState(true);
  const [notice,setNotice]=useState('');
  const revision=useRef(0);
  const clear=useCallback(()=>{
    revision.current++;setToken(null);setUser(null);
    localStorage.removeItem('agentos_token');localStorage.removeItem('agentos_user');
  },[]);
  const refresh=useCallback(async()=>{
    const rev=++revision.current;
    setChecking(true);
    try {
      const session=await restoreSession(localStorage,t=>new AgentOSClient(t).getProfile());
      if(rev!==revision.current)return;
      setToken(session?.token??null);setUser(session?.user??null);
    } catch(error) {
      if(rev!==revision.current)return;
      setToken(null);setUser(null);
      setNotice((error as {status?:number}).status===401 ? 'Your session has ended. Sign in to continue.' : 'We couldn’t verify your session. Reconnect and try again.');
    } finally {if(rev===revision.current)setChecking(false);}
  },[]);
  useEffect(()=>{
    void refresh();
    const expired=()=>{clear();setChecking(false);setNotice('Your session has ended. Sign in to continue.');};
    const changed=(e:StorageEvent)=>{if(e.key==='agentos_token'||e.key===null)void refresh();};
    window.addEventListener('agentos:session-expired',expired);
    window.addEventListener('storage',changed);
    return()=>{revision.current++;window.removeEventListener('agentos:session-expired',expired);window.removeEventListener('storage',changed);};
  },[refresh,clear]);
  const login=useCallback((newToken:string,profile:UserProfile)=>{
    revision.current++;const current=verifiedProfile(profile);
    localStorage.setItem('agentos_token',newToken);localStorage.removeItem('agentos_user');
    setToken(newToken);setUser(current);setNotice('');setChecking(false);
  },[]);
  const logout=useCallback(async()=>{
    const client=new AgentOSClient(token??undefined);
    clear();setChecking(true);
    try {await client.logout();setNotice('You’re signed out. See you next time.');}
    catch {setNotice('Signed out on this device. The server could not confirm session revocation.');}
    finally {setChecking(false);}
  },[token,clear]);
  return {token,user,checking,notice,login,logout,refresh};
}
