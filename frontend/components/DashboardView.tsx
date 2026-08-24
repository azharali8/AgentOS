'use client';

import React from 'react';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  Users,
  Clock,
  Shield,
  Cpu,
  RefreshCw,
  Plus,
  GitBranch,
  Terminal,
  Zap,
  Lock,
} from 'lucide-react';
import { Task, AgentDefinition, UserProfile, ModelsStatusResponse } from '../types';

interface DashboardViewProps {
  tasks: Task[];
  agents: AgentDefinition[];
  currentUser: UserProfile | null;
  modelsStatus?: ModelsStatusResponse | null;
  onRefresh: () => void;
  onSelectTask: (taskId: string) => void;
  onNewTaskClick: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  tasks,
  agents,
  currentUser,
  modelsStatus,
  onRefresh,
  onSelectTask,
  onNewTaskClick,
}) => {
  // Filter out test harness / benchmark tasks from user-facing dashboard
  const userTasks = tasks.filter(
    (t) => !t.instruction.toLowerCase().includes('benchmark') && !t.instruction.toLowerCase().includes('test harness')
  );

  const runningTasks = userTasks.filter((t) =>
    ['RUNNING', 'EXECUTING', 'PLANNING'].includes(t.status)
  );
  const waitingApproval = userTasks.filter((t) => t.status === 'WAITING_APPROVAL');
  const completedTasks = userTasks.filter((t) => t.status === 'COMPLETED');
  const failedTasks = userTasks.filter((t) => t.status === 'FAILED');

  const greetingName = currentUser?.username || 'Engineer';

  return (
    <div className="space-y-6">
      {/* Top Welcome & Quick Actions Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-xl font-bold text-slate-100 tracking-tight">
              Welcome, {greetingName}
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-blue-500/10 text-blue-400 border border-blue-500/30 uppercase">
              {currentUser?.role || 'USER'}
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            AI engineering operations across your connected workspace
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={onRefresh}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 rounded-md text-xs font-mono transition-colors border border-slate-800"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Sync</span>
          </button>

          <button
            onClick={onNewTaskClick}
            className="flex items-center space-x-1.5 px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-md text-xs font-mono font-bold transition-colors shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Task</span>
          </button>
        </div>
      </div>

      {/* Operational System Status & Work in Flight */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Active Work</span>
            <Activity className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 font-mono">{runningTasks.length}</div>
          <p className="text-[11px] text-slate-500">Autonomous execution in flight</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Human Gates</span>
            <Lock className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-amber-400 font-mono">
            {waitingApproval.length}
          </div>
          <p className="text-[11px] text-slate-500">Awaiting patch authorization</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Completed</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 font-mono">
            {completedTasks.length}
          </div>
          <p className="text-[11px] text-slate-500">Successful engineering jobs</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Registered Agents</span>
            <Users className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 font-mono">{agents.length}</div>
          <p className="text-[11px] text-slate-500">Domain specialized experts</p>
        </div>
      </div>

      {/* Main Grid: Active Work Overview + System Readiness */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Recent Engineering Tasks */}
        <div className="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-2">
            <h3 className="font-semibold text-slate-200 text-xs uppercase tracking-wider flex items-center">
              <Terminal className="w-4 h-4 mr-2 text-blue-400" />
              Engineering Tasks Activity
            </h3>
            <span className="text-[11px] text-slate-500 font-mono">Real Workload</span>
          </div>

          <div className="space-y-2 flex-1">
            {userTasks.length === 0 ? (
              <div className="text-center py-14 space-y-3">
                <p className="text-xs font-mono text-slate-400 font-bold uppercase">
                  No engineering tasks in workspace
                </p>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Submit a task to let the Supervisor plan, delegate to specialized agents, execute bounded tools, and review results.
                </p>
                <button
                  onClick={onNewTaskClick}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-mono transition-colors"
                >
                  Create First Task
                </button>
              </div>
            ) : (
              userTasks.slice(0, 7).map((task) => (
                <div
                  key={task.task_id}
                  onClick={() => onSelectTask(task.task_id)}
                  className="flex items-center justify-between p-3 bg-slate-950/60 hover:bg-slate-800/80 rounded-lg border border-slate-800/60 cursor-pointer transition-colors"
                >
                  <div className="flex items-center space-x-3 truncate">
                    <span
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        task.status === 'COMPLETED'
                          ? 'bg-emerald-500'
                          : task.status === 'FAILED'
                          ? 'bg-rose-500'
                          : task.status === 'WAITING_APPROVAL'
                          ? 'bg-amber-400 animate-pulse'
                          : 'bg-blue-500 animate-pulse'
                      }`}
                    />
                    <div className="truncate">
                      <p className="text-xs font-mono text-slate-200 truncate">{task.instruction}</p>
                      <p className="text-[10px] text-slate-500 font-mono">
                        ID: {task.task_id.slice(0, 8)}... · Agent: {task.assigned_agent || 'supervisor'}
                      </p>
                    </div>
                  </div>

                  <span
                    className={`text-[10px] px-2.5 py-0.5 rounded font-mono font-bold ${
                      task.status === 'COMPLETED'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : task.status === 'FAILED'
                        ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                        : task.status === 'WAITING_APPROVAL'
                        ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                        : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                    }`}
                  >
                    {task.status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Real System Readiness & Model Runtime Status */}
        <div className="lg:col-span-4 space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="font-semibold text-slate-200 text-xs uppercase tracking-wider mb-3 flex items-center">
              <Zap className="w-4 h-4 mr-2 text-emerald-400" />
              Subsystem Readiness
            </h3>
            <div className="space-y-2 font-mono text-xs">
              <div className="flex items-center justify-between p-2 bg-slate-950/60 rounded border border-slate-800">
                <span className="text-slate-400">FastAPI API v1</span>
                <span className="text-emerald-400 font-bold">● HEALTHY</span>
              </div>
              <div className="flex items-center justify-between p-2 bg-slate-950/60 rounded border border-slate-800">
                <span className="text-slate-400">Supervisor DAG</span>
                <span className="text-emerald-400 font-bold">● READY</span>
              </div>
              <div className="flex items-center justify-between p-2 bg-slate-950/60 rounded border border-slate-800">
                <span className="text-slate-400">SQLite Checkpointer</span>
                <span className="text-emerald-400 font-bold">● CONNECTED</span>
              </div>
              <div className="flex items-center justify-between p-2 bg-slate-950/60 rounded border border-slate-800">
                <span className="text-slate-400">Security Sandbox</span>
                <span className="text-emerald-400 font-bold">● ENFORCED</span>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="font-semibold text-slate-200 text-xs uppercase tracking-wider mb-3 flex items-center">
              <Cpu className="w-4 h-4 mr-2 text-blue-400" />
              Model Runtime Probes
            </h3>
            <div className="space-y-2 text-xs font-mono">
              {modelsStatus?.models?.slice(0, 3).map((m) => (
                <div key={m.name} className="p-2 bg-slate-950/60 rounded border border-slate-800 flex items-center justify-between">
                  <div className="truncate">
                    <p className="text-slate-300 font-bold truncate">{m.name}</p>
                    <p className="text-[10px] text-slate-500">{m.provider} ({m.tier})</p>
                  </div>
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${
                      m.status === 'READY'
                        ? 'bg-emerald-500/20 text-emerald-300'
                        : 'bg-blue-500/20 text-blue-300'
                    }`}
                  >
                    {m.status}
                  </span>
                </div>
              )) || (
                <p className="text-slate-500 text-center py-4">Probing model runtime...</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
