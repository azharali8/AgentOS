'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  Server,
  Layers,
  Activity,
  Database,
  Cpu,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { AgentOSClient } from '../../lib/api';

interface ObservabilityViewProps {
  client?: AgentOSClient;
}

interface ServiceRow {
  name: string;
  icon: React.ElementType;
  status: 'Healthy' | 'Degraded' | 'Unavailable' | 'Unknown';
  uptime: string;
  latency: string;
  traffic: string;
}

function statusColor(status: ServiceRow['status']) {
  switch (status) {
    case 'Healthy': return 'text-emerald-600';
    case 'Degraded': return 'text-amber-600';
    case 'Unavailable': return 'text-rose-600';
    default: return 'text-slate-400';
  }
}

function StatusIcon({ status }: { status: ServiceRow['status'] }) {
  switch (status) {
    case 'Healthy': return <CheckCircle2 className="w-3.5 h-3.5" />;
    case 'Degraded': return <AlertCircle className="w-3.5 h-3.5" />;
    case 'Unavailable': return <XCircle className="w-3.5 h-3.5" />;
    default: return <AlertCircle className="w-3.5 h-3.5" />;
  }
}

export const ObservabilityView: React.FC<ObservabilityViewProps> = ({ client }) => {
  const [services, setServices] = useState<ServiceRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState('');
  const [llmUsage, setLlmUsage] = useState<{ total_tokens?: number; total_cost_usd?: number } | null>(null);

  const loadMetrics = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      // Parallel fetch all system endpoints
      const [health, readiness, metrics, queue, workers] = await Promise.all([
        client.getHealth().catch(() => null),
        client.getReadiness().catch(() => null),
        client.getSystemMetrics().catch(() => null),
        client.getSystemQueue().catch(() => null),
        client.getSystemWorkers().catch(() => null),
      ]);

      const sysMetrics = (metrics as any)?.system_metrics ?? null;
      const llm = (metrics as any)?.llm_usage ?? null;
      setLlmUsage(llm);

      const apiStatus: ServiceRow['status'] =
        health?.status === 'HEALTHY' ? 'Healthy' :
        health?.status ? 'Degraded' : 'Unavailable';

      const dbStatus: ServiceRow['status'] =
        (readiness as any)?.database === true ? 'Healthy' :
        (readiness as any)?.database === false ? 'Unavailable' : 'Unknown';

      const agentsCount: number =
        (readiness as any)?.agents_count ?? (Array.isArray(workers) ? workers.length : null) ?? 0;
      const activeWorkers = Array.isArray(workers)
        ? workers.filter((w: any) => w.status === 'ACTIVE' || w.state === 'active').length
        : agentsCount;

      const queueStats = (queue as any)?.stats ?? null;
      const queueDepth: string = queueStats?.total != null
        ? `${queueStats.total} queued`
        : queueStats?.pending != null
        ? `${queueStats.pending} pending`
        : '—';

      const cpuPct: string = sysMetrics?.cpu_percent != null
        ? `${sysMetrics.cpu_percent.toFixed(1)}%`
        : '—';
      const memPct: string = sysMetrics?.memory_percent != null
        ? `${sysMetrics.memory_percent.toFixed(1)}%`
        : '—';

      const rows: ServiceRow[] = [
        {
          name: 'API Server',
          icon: Server,
          status: apiStatus,
          uptime: health?.status === 'HEALTHY' ? 'Online' : '—',
          latency: sysMetrics?.avg_response_ms != null ? `${sysMetrics.avg_response_ms}ms` : '—',
          traffic: sysMetrics?.requests_per_min != null ? `${sysMetrics.requests_per_min}/min` : '—',
        },
        {
          name: 'Worker Pool',
          icon: Layers,
          status: agentsCount > 0 ? 'Healthy' : dbStatus === 'Healthy' ? 'Healthy' : 'Unknown',
          uptime: agentsCount > 0 ? 'Online' : '—',
          latency: '—',
          traffic: `${activeWorkers} active`,
        },
        {
          name: 'Task Queue',
          icon: Activity,
          status: queueStats != null ? 'Healthy' : 'Unknown',
          uptime: queueStats != null ? 'Online' : '—',
          latency: '—',
          traffic: queueDepth,
        },
        {
          name: 'Database',
          icon: Database,
          status: dbStatus === 'Unknown' ? 'Unknown' : dbStatus,
          uptime: dbStatus === 'Healthy' ? 'Online' : '—',
          latency: '—',
          traffic: '—',
        },
        {
          name: 'System Resources',
          icon: Cpu,
          status: sysMetrics != null ? 'Healthy' : 'Unknown',
          uptime: sysMetrics != null ? 'Online' : '—',
          latency: `CPU ${cpuPct}`,
          traffic: `Mem ${memPct}`,
        },
      ];

      setServices(rows);
      setLastRefreshed(new Date().toLocaleTimeString());
    } catch (err) {
      console.error('Failed to load system metrics:', err);
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    loadMetrics();
    const interval = setInterval(loadMetrics, 15000);
    return () => clearInterval(interval);
  }, [loadMetrics]);

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Operations</h1>
          <p className="text-xs text-slate-500">
            Infrastructure health — live system metrics
          </p>
        </div>
        <button
          onClick={loadMetrics}
          disabled={loading}
          className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-semibold text-slate-600 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5" />
          )}
          <span>Refresh</span>
        </button>
      </div>

      {/* Services Table */}
      <div className="space-y-3">
        <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Services</h2>

        {!client ? (
          <div className="bg-white rounded-2xl border border-slate-200/90 p-12 flex flex-col items-center space-y-3 shadow-2xs">
            <AlertCircle className="w-8 h-8 text-slate-300" />
            <p className="text-sm font-medium text-slate-500">Not connected</p>
            <p className="text-xs text-slate-400">Sign in to view system status</p>
          </div>
        ) : loading && services.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200/90 p-12 flex flex-col items-center space-y-3 shadow-2xs">
            <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
            <p className="text-xs text-slate-400">Loading metrics…</p>
          </div>
        ) : (
          <div className="bg-white rounded-2xl border border-slate-200/90 divide-y divide-slate-100 shadow-2xs overflow-hidden">
            {services.map((svc) => {
              const Icon = svc.icon;
              return (
                <div
                  key={svc.name}
                  className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-xs font-sans hover:bg-slate-50/50 transition-colors"
                >
                  {/* Left: Service Identity */}
                  <div className="flex items-center space-x-3 w-48">
                    <div className="text-slate-400">
                      <Icon className="w-4 h-4" />
                    </div>
                    <span className="font-bold text-slate-900">{svc.name}</span>
                  </div>

                  {/* Status */}
                  <div className={`flex items-center space-x-1.5 font-semibold w-28 ${statusColor(svc.status)}`}>
                    <StatusIcon status={svc.status} />
                    <span>{svc.status}</span>
                  </div>

                  {/* Right: Metrics Grid */}
                  <div className="flex items-center space-x-8 sm:space-x-12 text-right">
                    <div className="w-20">
                      <div className="font-bold text-slate-900 font-mono">{svc.uptime}</div>
                      <div className="text-[10px] text-slate-400">Uptime</div>
                    </div>
                    <div className="w-20">
                      <div className="font-bold text-slate-900 font-mono">{svc.latency}</div>
                      <div className="text-[10px] text-slate-400">Latency</div>
                    </div>
                    <div className="w-24">
                      <div className="font-bold text-slate-900 font-mono">{svc.traffic}</div>
                      <div className="text-[10px] text-slate-400">Traffic</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* LLM Usage Summary (if available) */}
      {llmUsage && (
        <div className="space-y-3">
          <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider">LLM Usage</h2>
          <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-2xs flex items-center space-x-10">
            {llmUsage.total_tokens != null && (
              <div>
                <div className="text-lg font-extrabold text-slate-900 font-mono">
                  {llmUsage.total_tokens.toLocaleString()}
                </div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider">Total Tokens</div>
              </div>
            )}
            {llmUsage.total_cost_usd != null && (
              <div>
                <div className="text-lg font-extrabold text-slate-900 font-mono">
                  ${llmUsage.total_cost_usd.toFixed(4)}
                </div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider">Total Cost (USD)</div>
              </div>
            )}
          </div>
        </div>
      )}

      {lastRefreshed && (
        <p className="text-[10px] text-slate-400 text-right">
          Last refreshed {lastRefreshed}
        </p>
      )}
    </div>
  );
};