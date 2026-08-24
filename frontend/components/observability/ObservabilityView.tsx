'use client';

import React, { useState, useEffect } from 'react';
import {
  Activity,
  Cpu,
  BarChart3,
  RefreshCw,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Zap,
} from 'lucide-react';
import { AgentOSClient } from '../../lib/api';

interface ObservabilityViewProps {
  client: AgentOSClient;
}

export const ObservabilityView: React.FC<ObservabilityViewProps> = ({ client }) => {
  const [metrics, setMetrics] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMetrics = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await client.getSystemMetrics();
      setMetrics(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch observability telemetry');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMetrics();
    const interval = setInterval(loadMetrics, 10000);
    return () => clearInterval(interval);
  }, []);

  const sys = metrics?.system_metrics || {};
  const llm = metrics?.llm_usage || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">Platform Observability & Telemetry</h2>
          <p className="text-sm text-slate-400">
            Empirical runtime performance, agent execution latencies, and token consumption
          </p>
        </div>
        <button
          onClick={loadMetrics}
          className="flex items-center space-x-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-mono transition-colors border border-slate-700"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh Telemetry</span>
        </button>
      </div>

      {error && (
        <div className="p-3.5 bg-rose-950/40 border border-rose-800/40 rounded-xl text-rose-300 text-xs font-mono">
          Telemetry stream warning: {error}
        </div>
      )}

      {/* Primary Metrics Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Tokens</span>
            <Zap className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 font-mono">
            {llm.total_tokens_used ?? 0}
          </div>
          <p className="text-xs text-slate-500 mt-1">Prompt & Completion cumulative</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Estimated Cost</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 font-mono">
            ${(llm.total_estimated_cost_usd ?? 0).toFixed(4)}
          </div>
          <p className="text-xs text-slate-500 mt-1">LLM infrastructure spend</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Tracked Tools</span>
            <BarChart3 className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 font-mono">
            {Object.keys(sys.tool_executions || {}).length}
          </div>
          <p className="text-xs text-slate-500 mt-1">Monitored tool execution counters</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Agent Calls</span>
            <Cpu className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 font-mono">
            {Number(Object.values(sys.agent_invocations || {}).reduce((a: number, b: any) => a + Number(b || 0), 0))}
          </div>
          <p className="text-xs text-slate-500 mt-1">Domain agent dispatch count</p>
        </div>
      </div>

      {/* Raw Metrics & Telemetry Breakdowns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col h-80">
          <h3 className="font-semibold text-slate-200 text-xs uppercase tracking-wider mb-3">
            Tool Execution Telemetry
          </h3>
          <div className="flex-1 bg-slate-950 border border-slate-800/80 rounded-lg p-3 font-mono text-xs overflow-y-auto space-y-2">
            {Object.keys(sys.tool_executions || {}).length === 0 ? (
              <p className="text-slate-500 text-center py-10">No tool execution telemetry recorded.</p>
            ) : (
              Object.entries(sys.tool_executions || {}).map(([tool, count]) => (
                <div key={tool} className="flex items-center justify-between p-2 bg-slate-900/60 rounded border border-slate-800/60">
                  <span className="text-slate-300 font-bold">{tool}</span>
                  <span className="text-blue-400">{count as number} executions</span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col h-80">
          <h3 className="font-semibold text-slate-200 text-xs uppercase tracking-wider mb-3">
            Agent Dispatch Distribution
          </h3>
          <div className="flex-1 bg-slate-950 border border-slate-800/80 rounded-lg p-3 font-mono text-xs overflow-y-auto space-y-2">
            {Object.keys(sys.agent_invocations || {}).length === 0 ? (
              <p className="text-slate-500 text-center py-10">No agent dispatch records available.</p>
            ) : (
              Object.entries(sys.agent_invocations || {}).map(([agent, count]) => (
                <div key={agent} className="flex items-center justify-between p-2 bg-slate-900/60 rounded border border-slate-800/60">
                  <span className="text-slate-300 font-bold">{agent}</span>
                  <span className="text-purple-400">{count as number} invocations</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};