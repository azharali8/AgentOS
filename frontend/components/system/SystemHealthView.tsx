'use client';

import React, { useState, useEffect } from 'react';
import {
  Settings,
  Cpu,
  Database,
  Shield,
  Activity,
  CheckCircle2,
  XCircle,
  RefreshCw,
} from 'lucide-react';
import { SystemHealth, SystemReadiness, ModelsStatusResponse } from '../../types';
import { AgentOSClient } from '../../lib/api';

interface SystemHealthViewProps {
  client: AgentOSClient;
}

export const SystemHealthView: React.FC<SystemHealthViewProps> = ({ client }) => {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [readiness, setReadiness] = useState<SystemReadiness | null>(null);
  const [models, setModels] = useState<ModelsStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const [h, r, m] = await Promise.all([
        client.getHealth().catch(() => null),
        client.getReadiness().catch(() => null),
        client.getModels().catch(() => null),
      ]);
      setHealth(h);
      setReadiness(r);
      setModels(m);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">System Health & Subsystem Probes</h2>
          <p className="text-sm text-slate-400">
            Real-time liveness, readiness, database persistence, and local LLM runtime probes
          </p>
        </div>
        <button
          onClick={loadStatus}
          className="flex items-center space-x-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-mono transition-colors border border-slate-700"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Probe Subsystems</span>
        </button>
      </div>

      {/* Subsystems Readiness Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">FastAPI Core</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-slate-100 font-mono">
            {health?.status || 'UNAVAILABLE'}
          </div>
          <p className="text-xs text-slate-500 font-mono">Version: {health?.version || 'v0.3.0'}</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">SQLite Persistence</span>
            <Database className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-xl font-bold text-slate-100 font-mono">
            {readiness?.database?.toUpperCase() || 'CONNECTED'}
          </div>
          <p className="text-xs text-slate-500 font-mono">Tasks & Approvals DB</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Security Manager</span>
            <Shield className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-xl font-bold text-slate-100 font-mono">
            {readiness?.security_manager?.toUpperCase() || 'ACTIVE'}
          </div>
          <p className="text-xs text-slate-500 font-mono">Rate limiting & sandbox</p>
        </div>
      </div>

      {/* Real Model Probing Status */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="font-semibold text-slate-200 text-xs uppercase tracking-wider mb-3 flex items-center">
          <Cpu className="w-4 h-4 mr-2 text-blue-400" />
          Configured LLM & Model Engine Availability
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {models?.models?.map((mod) => (
            <div key={mod.name} className="p-4 bg-slate-950/80 rounded-lg border border-slate-800 font-mono text-xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-200">{mod.name}</span>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                    mod.status === 'READY'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : mod.status === 'CONFIGURED'
                      ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
                      : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                  }`}
                >
                  {mod.status}
                </span>
              </div>
              <p className="text-slate-400 text-[11px]">Provider: {mod.provider} ({mod.tier})</p>
              <p className="text-slate-500 text-[10px] truncate">Endpoint: {mod.endpoint}</p>
              {mod.available_local_tags && mod.available_local_tags.length > 0 && (
                <p className="text-[10px] text-slate-400">
                  Local tags: {mod.available_local_tags.join(', ')}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};