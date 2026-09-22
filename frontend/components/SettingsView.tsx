"use client";
import {modelLabel} from '../lib/model-label';
import {UserProfile} from '../types';
import {WorkspaceSettings} from '../hooks/useWorkspaceSettings';
import {ModelSelector} from './ModelSelector';
export {ModelSelector} from './ModelSelector';
export function SettingsView({user,onSignOut,preferences}:{user:UserProfile;onSignOut:()=>void;preferences:WorkspaceSettings}) {
 return <div className="settings-view"><header><h1>Settings</h1><p>Make AgentOS work your way.</p></header>
 <section><h2>Account</h2><div className="account-row"><div><strong>{user.username}</strong><p>{user.email}</p><p>{user.role.toLowerCase()} · Signed in</p></div><button onClick={onSignOut}>Sign out</button></div></section>
 <section><h2>Appearance</h2><p>Choose your workspace theme.</p><div className="theme-options" role="radiogroup" aria-label="Theme">{(['light','dark','system'] as const).map(t=><button key={t} role="radio" aria-checked={preferences.theme===t} onClick={()=>preferences.setTheme(t)}>{t[0].toUpperCase()+t.slice(1)}</button>)}</div></section>
 <section><div className="settings-section-title"><h2>AI model</h2><button onClick={()=>void preferences.refresh()} disabled={preferences.busy}>Refresh</button></div><p>Ollama model for future workspace requests. Cloud models send requests through your Ollama cloud account. Shared by Settings and the command composer.</p>
 <ModelSelector preferences={preferences} disabled={user.role==='VIEWER'}/>
 {preferences.models?.status==='offline'&&<p role="alert">Ollama is offline. Start Ollama, then refresh.</p>}
 {preferences.models&&!preferences.models.selection_enabled&&<p>The workspace uses {preferences.models.provider}. Local selection is available when the configured provider is Ollama.</p>}
 {preferences.models?.models.map(m=><div className="model-row" key={m.name}><span title={m.name}>{modelLabel(m.name)}<small>{m.cloud?'Cloud · requires Ollama sign-in':m.recommended?'Lightweight local option':m.selectable?'Local model':m.status==='Unavailable'?'Could not verify model. Try refreshing.':'Embedding / unsupported for chat'}</small></span><span>{m.status}</span></div>)}
 {preferences.models?.status==='online'&&!preferences.models.models.length&&<p>No Ollama models available. Install a compatible chat model in Ollama, then refresh.</p>}
 {preferences.error&&<p role="alert">{preferences.error}</p>}
 </section>
 <section><h2>Voice</h2><label className="account-row"><span>Read Live Voice responses aloud<small>You can interrupt by speaking.</small></span><input type="checkbox" checked={preferences.readAloud} onChange={e=>preferences.setReadAloud(e.target.checked)}/></label></section>
 </div>;
}
