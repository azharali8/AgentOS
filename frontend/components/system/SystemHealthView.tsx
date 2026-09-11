'use client';

import React, { useEffect, useState } from 'react';
import { AgentOSClient } from '../../lib/api';

interface SystemHealthViewProps { client?: AgentOSClient }

export const SystemHealthView: React.FC<SystemHealthViewProps> = ({ client }) => {
  const [info, setInfo] = useState<{ provider: string; model: string; speech: string; configured: boolean; status: string; modelError?: string | null } | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let disposed = false;
    setError(''); setInfo(null);
    if (!client) return;
    Promise.all([client.getModels(), client.getVoiceStatus()]).then(([models, voice]) => {
      if (!disposed) setInfo({provider: models.active_provider, model: models.configured_model,
        speech: voice.stt_provider, configured: voice.has_api_key, status: models.status, modelError: models.error});
    }).catch(err => { if (!disposed) setError(err instanceof Error ? err.message : 'Could not load settings'); });
    return () => { disposed = true; };
  }, [client, attempt]);
  return <section className="max-w-3xl mx-auto bg-white rounded-2xl border border-slate-200 p-6 space-y-5">
    <div><h1 className="text-xl font-bold">Settings</h1>
      <p className="text-sm text-slate-500 mt-1">Current server configuration. Ask your administrator to change these settings.</p></div>
    {error ? <div role="alert" className="text-sm text-rose-700">{error}
      <button className="block mt-2 underline" onClick={() => setAttempt(n => n + 1)}>Retry</button></div>
      : !info ? <p role="status" className="text-sm text-slate-500">Loading configuration…</p>
      : <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <div><dt className="text-slate-500">Model provider</dt><dd>{info.provider}</dd></div>
        <div><dt className="text-slate-500">Configured model</dt><dd>{info.model || 'Not configured'}</dd></div>
        <div className="sm:col-span-2"><dt className="text-slate-500">Model availability</dt><dd>{info.status}</dd>
          {info.modelError && <p role="alert" className="text-rose-700 mt-1">{info.modelError}</p>}</div>
        <div><dt className="text-slate-500">Speech recognition</dt><dd>{info.speech}</dd></div>
        <div><dt className="text-slate-500">AssemblyAI key</dt><dd>{info.configured ? 'Configured' : 'Not configured'}</dd></div>
      </dl>}
    <p className="text-sm text-slate-600">AgentOS applies the server’s security policies to every task. Review pending changes in Approvals. Speech playback can be muted from the Voice control.</p>
  </section>;
};
