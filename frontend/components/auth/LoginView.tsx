'use client';

import React, {useEffect, useState} from 'react';
import Link from 'next/link';
import {ArrowRight, ArrowUpRight, Check, Code2, Eye, EyeOff, GitBranch, Layers3, Loader2, LockKeyhole, Mail, ShieldCheck, Sparkles, Terminal, Workflow} from 'lucide-react';
import {AgentOSClient} from '../../lib/api';
import {authError} from '../../lib/auth-session';
import {registrationPasswordError, registrationPasswordChecks} from '../../lib/registration-password';
import {UserProfile} from '../../types';

interface LoginViewProps {
  onLoginSuccess: (token:string,user:UserProfile)=>void;
  notice?:string;
  onRetrySession?:()=>void;
}
export const LoginView:React.FC<LoginViewProps>=({onLoginSuccess,notice,onRetrySession})=>{
  const [identifier,setIdentifier]=useState('');
  const [password,setPassword]=useState('');
  const [name,setName]=useState('');
  const [visible,setVisible]=useState(false);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [registration,setRegistration]=useState(false);
  const [signup,setSignup]=useState(false);
  const passwordChecks=registrationPasswordChecks(password);
  useEffect(()=>{
    let active=true;
    new AgentOSClient().authOptions().then(options=>{if(active)setRegistration(options.registration_enabled);}).catch(()=>{});
    return()=>{active=false;};
  },[]);
  const submit=async(e:React.FormEvent)=>{
    e.preventDefault();if(loading)return;
    if(signup){const passwordError=registrationPasswordError(password);if(passwordError){setError(passwordError);return;}}
    setLoading(true);setError('');setMessage('');
    try {
      const client=new AgentOSClient();
      if(signup){
        await client.register(identifier.trim(),name.trim(),password);
        setSignup(false);setPassword('');setMessage('Your local account is ready. Sign in to open your workspace.');
      } else {
        const result=await client.login(identifier.trim(),password);
        onLoginSuccess(result.token,{user_id:result.user_id,username:result.username,email:result.email,role:result.role,is_authenticated:true});
      }
    } catch(err){setError(authError(err));}
    finally {setLoading(false);}
  };
  return <main className="auth-page">
    <section className="auth-story" aria-labelledby="product-heading">
      <Link href="/" className="auth-brand" aria-label="AgentOS home"><span className="auth-logo"><Sparkles size={21}/></span>AgentOS<span className="auth-brand-tag">ENGINEERING, ORCHESTRATED.</span></Link>
      <div className="auth-story-content">
        <p className="auth-eyebrow"><span/> YOUR IDEAS. A WHOLE ENGINEERING TEAM.</p>
        <h1 id="product-heading">Build software.<br/>With a team<br/><span>that thinks ahead.</span></h1>
        <p className="auth-description">One instruction. A coordinated workflow.<br className="hidden xl:block"/> AgentOS brings planning, coding, testing and review together — with you in control.</p>
        <div className="auth-workflow" role="img" aria-label="Voice or text instructions reach the Supervisor, which coordinates planning, coding, testing and review.">
          <div className="auth-workflow-top"><span><Terminal size={14}/> Voice or text instruction</span><span className="auth-workflow-label">THE WORKFLOW</span></div>
          <div className="auth-connector"/>
          <div className="auth-supervisor"><span className="auth-supervisor-icon"><Workflow size={25}/></span><div><strong>Supervisor</strong><p>Your direction. Coordinated execution.</p></div><span className="auth-supervisor-mark"><Sparkles size={16}/></span></div>
          <div className="auth-branches"/>
          <div className="auth-workflow-steps">{[{label:'Plan',icon:GitBranch},{label:'Code',icon:Code2},{label:'Test',icon:Check},{label:'Review',icon:ShieldCheck}].map(({label,icon:Icon})=><div key={label}><Icon size={18}/><span>{label}</span></div>)}</div>
          <div className="auth-workflow-bottom"><Layers3 size={14}/><span>From an idea to reviewed software.</span></div>
        </div>
      </div>
      <div className="auth-story-footer"><span className="auth-footer-line"/><p>Built for the way engineers work.</p></div>
    </section>
    <section className="auth-entry" aria-labelledby="auth-heading">
      <div className="auth-entry-top"><span className="auth-entry-dot"/> THE AGENTOS WORKSPACE</div>
      <div className="auth-form-wrap">
        <span className="auth-form-icon"><ArrowUpRight size={25}/></span>
        <p className="auth-kicker">LET’S BUILD SOMETHING GREAT</p>
        <h2 id="auth-heading">{signup?'Create your account.':'Welcome back.'}</h2>
        <p className="auth-form-description">{signup?'Create a local account for this workspace.':'Sign in to pick up where your ideas left off.'}</p>
        {(message||notice)&&<div className="auth-notice" role="status">{message||notice}{notice?.includes('verify')&&onRetrySession&&<button type="button" onClick={onRetrySession}>Retry connection</button>}</div>}
        {error&&<div id="auth-error" className="auth-error" role="alert">{error}</div>}
        <form onSubmit={submit} aria-busy={loading} className="auth-form">
          {signup&&<div><label htmlFor="auth-name">Your name</label><div className="auth-input-wrap"><input id="auth-name" autoComplete="name" value={name} onChange={e=>setName(e.target.value)} required minLength={3} maxLength={60} disabled={loading} placeholder="How should we address you?"/></div></div>}
          <div><label htmlFor="auth-identifier">{signup?'Email address':'Email or username'}</label><div className="auth-input-wrap"><Mail size={18} aria-hidden="true"/><input id="auth-identifier" type={signup?'email':'text'} autoComplete="username" value={identifier} onChange={e=>setIdentifier(e.target.value)} required maxLength={254} disabled={loading} placeholder={signup?'you@example.com':'Your email or username'} aria-invalid={!!error} aria-describedby={error?'auth-error':undefined}/></div></div>
          <div><label htmlFor="auth-password">Password</label><div className="auth-input-wrap"><LockKeyhole size={18} aria-hidden="true"/><input id="auth-password" type={visible?'text':'password'} autoComplete={signup?'new-password':'current-password'} value={password} onChange={e=>{setPassword(e.target.value);setError('');}} required minLength={signup?undefined:1} maxLength={signup?undefined:1024} disabled={loading} placeholder={signup?'Create a password':'Enter your password'} aria-invalid={!!error || (signup && password.length > 0 && !!registrationPasswordError(password))} aria-describedby={signup?'auth-password-help':error?'auth-error':undefined}/><button type="button" aria-label={visible?'Hide password':'Show password'} aria-pressed={visible} disabled={loading} onClick={()=>setVisible(!visible)}>{visible?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></div>
          {signup&&<div id="auth-password-help" className="auth-password-help" aria-live="polite" aria-atomic="true">
            <div className="auth-password-help-heading"><strong>Password requirements</strong><span>{passwordChecks.count}/20 characters</span></div>
            <p data-met={passwordChecks.length}><span aria-hidden="true">{passwordChecks.length?'✓':'○'}</span> 8–20 characters{passwordChecks.length?' — met':''}</p>
            <p data-met={passwordChecks.special}><span aria-hidden="true">{passwordChecks.special?'✓':'○'}</span> At least one special character, e.g. ! @ # ${passwordChecks.special?' — met':''}</p>
            {password.length>0&&<p className="auth-password-feedback">{passwordChecks.length&&passwordChecks.special?'Your password meets the requirements.':passwordChecks.count<8?`Add ${8-passwordChecks.count} more character${8-passwordChecks.count===1?'':'s'} to reach the minimum.`:passwordChecks.count>20?'Use no more than 20 characters.':'Add a special character such as !, @, # or $.'}</p>}
          </div>}
          {signup&&<p className="auth-local-note">Local accounts last for this server session. Durable accounts and email recovery are not available yet.</p>}
          <button className="auth-submit" type="submit" disabled={loading}>{loading?<><Loader2 className="animate-spin motion-reduce:animate-none" size={18}/>{signup?'Creating your account…':'Signing you in…'}</>:<>{signup?'Create local account':'Open your workspace'}<ArrowRight size={18}/></>}</button>
        </form>
        {registration?<p className="auth-switch">{signup?'Already have an account?':'New to this workspace?'} <button disabled={loading} onClick={()=>{setSignup(!signup);setError('');setMessage('');setPassword('');setVisible(false);}}>{signup?'Sign in':'Create account'}</button></p>:<p className="auth-switch">Use the account provided by your workspace administrator.</p>}
        <div className="auth-assurance"><ShieldCheck size={16}/><span>Your workspace. Your permissions. Your control.</span></div>
      </div>
      <footer className="auth-entry-footer"><span>AgentOS</span><span>AI Software Engineering Platform</span></footer>
    </section>
  </main>;
};
