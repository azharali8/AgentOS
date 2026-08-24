'use client';

import React, { useState, useMemo } from 'react';
import {
  Bot,
  Shield,
  Play,
  CheckCircle,
  XCircle,
  Lock,
  Terminal,
  Cpu,
  Clock,
  ChevronDown,
  ChevronRight,
  Info,
  AlertTriangle,
} from 'lucide-react';
import { AgentDefinition, UserRole, Task } from '../types';

interface AgentCenterViewProps {
  agents: AgentDefinition[];
  userRole: UserRole;
  tasks?: Task[];
  onInvokeAgent: (agentId: string, instruction: string) => Promise<any>;
}

// ─── Agent metrics from real task history ─────────────────────────────────────

function agentMetrics(agent: AgentDefinition, tasks: Task[]) {
  const agentTasks = tasks.filter(
    (t) =>
      (t as any).agent === agent.name ||
      (t as any).agent === agent.agent_type ||
      (t as any).requested_agent === agent.agent_type ||
      (t as any).requested_agent === agent.name
  );
  const total = agentTasks.length;
  const completed = agentTasks.filter((t) => t.status === 'COMPLETED').length;
  const failed = agentTasks.filter((t) => t.status === 'FAILED').length;
  const successRate = total > 0 ? Math.round((completed / total) * 100) : null;
  return { total, completed, failed, successRate };
}

// ─── Risk level badge ─────────────────────────────────────────────────────────

function riskBadge(level: string) {
  const map: Record<string, string> = {
    low: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    medium: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    high: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    critical: 'bg-rose-700/20 text-rose-300 border-rose-700/40',
  };
  return map[level.toLowerCase()] ?? 'bg-slate-500/10 text-slate-400 border-slate-500/30';
}

// ─── Agent Card ───────────────────────────────────────────────────────────────

const AgentCard: React.FC<{
  agent: AgentDefinition;
  userRole: UserRole;
  tasks: Task[];
  onInvoke: () => void;
}> = ({ agent, userRole, tasks, onInvoke }) => {
  const [expanded, setExpanded] = useState(false);
  const isCyber = agent.agent_type === 'cybersecurity';
  const isAdminOnly = isCyber;
  const isRestricted = isAdminOnly && userRole !== 'ADMIN';
  const metrics = useMemo(() => agentMetrics(agent, tasks), [agent, tasks]);

  return (
    <div
      className={`bg-slate-900 border rounded-xl flex flex-col transition-all ${
        isRestricted ? 'border-slate-800/50 opacity-70' : 'border-slate-800 hover:border-slate-700'
      }`}
    >
      {/* Card header */}
      <div className="p-5 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-slate-800 border border-slate-700">
              {isAdminOnly ? (
                <Shield className="w-4 h-4 text-rose-400" />
              ) : (
                <Bot className="w-4 h-4 text-blue-400" />
              )}
            </div>
            <div>
              <h3 className="font-bold text-slate-200 capitalize text-sm leading-tight">
                {agent.name.replace(/_/g, ' ')}
              </h3>
              <span className="text-[10px] text-slate-500 font-mono">{agent.agent_type}</span>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            {isAdminOnly && (
              <span className="text-[9px] bg-rose-500/10 text-rose-400 border border-rose-500/30 px-2 py-0.5 rounded font-mono font-bold flex items-center gap-1">
                <Lock className="w-2.5 h-2.5" />
                ADMIN ONLY
              </span>
            )}
            <span
              className={`text-[9px] px-2 py-0.5 rounded border font-mono font-semibold uppercase ${riskBadge(
                agent.risk_level
              )}`}
            >
              {agent.risk_level} risk
            </span>
          </div>
        </div>

        {/* Description */}
        <p className="text-xs text-slate-400 leading-relaxed">{agent.description}</p>

        {/* Runtime metrics */}
        <div className="grid grid-cols-3 gap-2 bg-slate-950/60 rounded-lg p-2.5 border border-slate-800/80">
          <div className="text-center">
            <div className="text-base font-bold font-mono text-slate-200">
              {metrics.total > 0 ? metrics.total : '—'}
            </div>
            <div className="text-[9px] text-slate-500 uppercase tracking-wider">Tasks</div>
          </div>
          <div className="text-center border-x border-slate-800/80">
            <div
              className={`text-base font-bold font-mono ${
                metrics.successRate === null
                  ? 'text-slate-500'
                  : metrics.successRate >= 80
                  ? 'text-emerald-400'
                  : metrics.successRate >= 50
                  ? 'text-amber-400'
                  : 'text-rose-400'
              }`}
            >
              {metrics.successRate !== null ? `${metrics.successRate}%` : '—'}
            </div>
            <div className="text-[9px] text-slate-500 uppercase tracking-wider">Success</div>
          </div>
          <div className="text-center">
            <div className="text-base font-bold font-mono text-slate-200">
              {agent.max_execution_time}s
            </div>
            <div className="text-[9px] text-slate-500 uppercase tracking-wider">Max TTL</div>
          </div>
        </div>
      </div>

      {/* Capabilities accordion */}
      <div className="border-t border-slate-800/80">
        <button
          onClick={() => setExpanded((x) => !x)}
          className="w-full px-5 py-2.5 flex items-center justify-between text-[11px] font-semibold text-slate-500 hover:text-slate-300 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <Terminal className="w-3 h-3" />
            Capabilities ({agent.capabilities.length})
          </span>
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
        </button>
        {expanded && (
          <div className="px-5 pb-3 flex flex-wrap gap-1.5">
            {agent.capabilities.map((cap) => (
              <span
                key={cap}
                className="text-[10px] bg-slate-950 px-2 py-0.5 rounded border border-slate-800 text-slate-400 font-mono"
              >
                {cap}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Footer action */}
      <div className="px-5 pb-4 pt-2">
        <button
          onClick={onInvoke}
          disabled={isRestricted}
          className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-medium font-mono transition-colors ${
            isRestricted
              ? 'bg-slate-800/60 text-slate-600 cursor-not-allowed'
              : 'bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 border border-blue-500/30 hover:border-blue-500/50'
          }`}
        >
          {isRestricted ? (
            <>
              <Lock className="w-3.5 h-3.5" />
              Restricted — Admin Required
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5" />
              Direct Invoke
            </>
          )}
        </button>
      </div>
    </div>
  );
};

// ─── Main View ────────────────────────────────────────────────────────────────

export const AgentCenterView: React.FC<AgentCenterViewProps> = ({
  agents,
  userRole,
  tasks = [],
  onInvokeAgent,
}) => {
  const [selectedAgent, setSelectedAgent] = useState<AgentDefinition | null>(null);
  const [instruction, setInstruction] = useState('');
  const [invokeResult, setInvokeResult] = useState<any | null>(null);
  const [isInvoking, setIsInvoking] = useState(false);
  const [invokeError, setInvokeError] = useState<string | null>(null);

  const handleInvoke = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent || !instruction.trim()) return;
    setIsInvoking(true);
    setInvokeError(null);
    setInvokeResult(null);

    try {
      const res = await onInvokeAgent(selectedAgent.name, instruction.trim());
      setInvokeResult(res);
    } catch (err: any) {
      setInvokeError(err.message || 'Invocation failed');
    } finally {
      setIsInvoking(false);
    }
  };

  // Platform-level summary stats
  const totalAgentTasks = useMemo(() => {
    return tasks.filter((t) => (t as any).agent || (t as any).requested_agent).length;
  }, [tasks]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">Specialized Agent Platform</h2>
          <p className="text-sm text-slate-400 mt-0.5">
            Bounded domain experts operating under Supervisor governance and SecurityManager
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-2xl font-bold font-mono text-slate-200">{agents.length}</div>
          <div className="text-xs text-slate-500">registered agents</div>
        </div>
      </div>

      {/* No agents empty state */}
      {agents.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed border-slate-800 rounded-xl text-center">
          <Bot className="w-10 h-10 text-slate-700 mb-4" />
          <p className="text-slate-400 font-medium">No agents registered</p>
          <p className="text-xs text-slate-600 mt-1">
            Start the backend to load the AgentOS agent registry.
          </p>
        </div>
      )}

      {/* Agent grid */}
      {agents.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <AgentCard
              key={agent.name}
              agent={agent}
              userRole={userRole}
              tasks={tasks}
              onInvoke={() => {
                setSelectedAgent(agent);
                setInvokeResult(null);
                setInvokeError(null);
                setInstruction('');
              }}
            />
          ))}
        </div>
      )}

      {/* Direct Invoke Modal */}
      {selectedAgent && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-100 capitalize">
                  Invoke {selectedAgent.name.replace(/_/g, ' ')}
                </h3>
                <span className="text-xs text-slate-500 font-mono">Domain: {selectedAgent.agent_type}</span>
              </div>
              <button
                onClick={() => setSelectedAgent(null)}
                className="text-slate-500 hover:text-slate-300 text-lg font-mono leading-none"
              >
                ✕
              </button>
            </div>

            {selectedAgent.agent_type === 'cybersecurity' && userRole === 'ADMIN' && (
              <div className="flex items-start gap-2 p-3 bg-amber-950/30 border border-amber-800/40 rounded-lg text-xs text-amber-300">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  Direct security agent invocations are logged and subject to cryptographic audit.
                  All actions run under SecurityManager policy enforcement.
                </span>
              </div>
            )}

            <form onSubmit={handleInvoke} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                  Instruction for Agent
                </label>
                <textarea
                  rows={3}
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder={`Enter specific instruction for ${selectedAgent.name}...`}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono text-xs"
                  required
                />
              </div>

              {invokeError && (
                <div className="p-3 bg-rose-950/40 border border-rose-800/40 rounded-lg text-xs text-rose-300 font-mono">
                  {invokeError}
                </div>
              )}

              {invokeResult && (
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1 font-mono text-xs">
                  <div className="text-emerald-400 font-bold flex items-center gap-1.5">
                    <CheckCircle className="w-3.5 h-3.5" />
                    Status: {invokeResult.status}
                  </div>
                  {invokeResult.summary && (
                    <div className="text-slate-300 mt-1">{invokeResult.summary}</div>
                  )}
                </div>
              )}

              <div className="flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setSelectedAgent(null)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium rounded-lg transition-colors"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={isInvoking}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                >
                  {isInvoking ? 'Executing...' : 'Invoke Agent'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
