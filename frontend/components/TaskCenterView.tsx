'use client';

import React, { useState, useMemo } from 'react';
import {
  Plus,
  Search,
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  GitBranch,
  FolderGit2,
  Bot,
  AlertTriangle,
  ChevronRight,
  Ban,
  Hourglass,
  Zap,
  LayoutList,
  SlidersHorizontal,
} from 'lucide-react';
import { Task, AgentDefinition } from '../types';

interface TaskCenterViewProps {
  tasks: Task[];
  agents: AgentDefinition[];
  onCreateTask: (
    instruction: string,
    priority: number,
    options?: { requested_agent?: string; execution_mode?: string }
  ) => Promise<void>;
  onSelectTask: (taskId: string) => void;
  onCancelTask: (taskId: string) => Promise<void>;
}

// ─── Status metadata ─────────────────────────────────────────────────────────

const STATUS_META: Record<
  string,
  { label: string; color: string; icon: React.ReactNode; pulse?: boolean }
> = {
  PENDING: {
    label: 'PENDING',
    color: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
    icon: <Hourglass className="w-3 h-3" />,
  },
  PLANNING: {
    label: 'PLANNING',
    color: 'bg-violet-500/10 text-violet-400 border-violet-500/30',
    icon: <Zap className="w-3 h-3" />,
    pulse: true,
  },
  EXECUTING: {
    label: 'EXECUTING',
    color: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    icon: <Play className="w-3 h-3" />,
    pulse: true,
  },
  WAITING_APPROVAL: {
    label: 'APPROVAL GATE',
    color: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    icon: <AlertTriangle className="w-3 h-3" />,
    pulse: true,
  },
  COMPLETED: {
    label: 'COMPLETED',
    color: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    icon: <CheckCircle2 className="w-3 h-3" />,
  },
  FAILED: {
    label: 'FAILED',
    color: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    icon: <XCircle className="w-3 h-3" />,
  },
  CANCELLED: {
    label: 'CANCELLED',
    color: 'bg-slate-600/10 text-slate-500 border-slate-600/20',
    icon: <Ban className="w-3 h-3" />,
  },
};

const ACTIVE_STATUSES = ['PENDING', 'PLANNING', 'EXECUTING', 'WAITING_APPROVAL'];

function elapsedLabel(isoDate: string): string {
  const diff = Math.floor((Date.now() - new Date(isoDate).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

// ─── Task Card ────────────────────────────────────────────────────────────────

const TaskCard: React.FC<{
  task: Task;
  onSelect: () => void;
  onCancel: () => void;
}> = ({ task, onSelect, onCancel }) => {
  const meta = STATUS_META[task.status] ?? {
    label: task.status,
    color: 'bg-slate-100 text-slate-700 border-slate-200',
    icon: <Clock className="w-3 h-3" />,
  };
  const isActive = ACTIVE_STATUSES.includes(task.status);
  const agentLabel = (task as any).agent ?? (task as any).requested_agent ?? null;

  return (
    <div
      className={`group bg-white border rounded-2xl p-5 flex flex-col gap-3 transition-all cursor-pointer hover:border-slate-300 hover:shadow-xs shadow-2xs ${
        task.status === 'WAITING_APPROVAL'
          ? 'border-amber-300 ring-2 ring-amber-50'
          : task.status === 'FAILED'
          ? 'border-rose-200'
          : 'border-slate-200/90'
      }`}
      onClick={onSelect}
    >
      {/* Top row: ID + status badge */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-slate-400 shrink-0">
          #{task.task_id.slice(0, 8)}
        </span>
        <span
          className={`inline-flex items-center gap-1 text-[10px] font-bold font-mono px-2 py-0.5 rounded-md border ${meta.color} ${
            meta.pulse ? 'animate-pulse' : ''
          }`}
        >
          {meta.icon}
          {meta.label}
        </span>
      </div>

      {/* Instruction */}
      <p className="text-sm font-semibold text-slate-900 leading-snug line-clamp-2">
        {task.instruction}
      </p>

      {/* Meta row: agent + elapsed */}
      <div className="flex items-center gap-3 flex-wrap">
        {agentLabel && (
          <span className="inline-flex items-center gap-1 text-[10px] text-indigo-600 font-mono bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded">
            <Bot className="w-3 h-3" />
            {agentLabel}
          </span>
        )}
        {task.status === 'WAITING_APPROVAL' && (
          <span className="inline-flex items-center gap-1 text-[10px] text-amber-700 font-mono font-bold">
            <AlertTriangle className="w-3 h-3" />
            Approval required
          </span>
        )}
        <span className="ml-auto text-[10px] text-slate-400 font-mono flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {elapsedLabel(task.created_at)}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSelect();
          }}
          className="flex items-center gap-1 text-[11px] font-mono text-slate-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-slate-50 transition-colors"
        >
          <ChevronRight className="w-3.5 h-3.5" />
          Inspect
        </button>
        {isActive && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onCancel();
            }}
            className="flex items-center gap-1 text-[11px] font-mono text-rose-600 hover:text-rose-700 px-2 py-1 rounded hover:bg-rose-50 transition-colors"
          >
            <Ban className="w-3 h-3" />
            Cancel
          </button>
        )}
      </div>
    </div>
  );
};

// ─── Main View ────────────────────────────────────────────────────────────────

export const TaskCenterView: React.FC<TaskCenterViewProps> = ({
  tasks,
  agents,
  onCreateTask,
  onSelectTask,
  onCancelTask,
}) => {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [priority, setPriority] = useState(1);
  const [executionMode, setExecutionMode] = useState('autonomous');
  const [branch, setBranch] = useState('main');
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!instruction.trim()) return;
    setIsSubmitting(true);
    try {
      await onCreateTask(instruction.trim(), priority, {
        execution_mode: executionMode,
      });
      setInstruction('');
      setShowCreateModal(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      const matchesStatus = filterStatus === 'ALL' || t.status === filterStatus;
      const matchesSearch =
        t.instruction.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.task_id.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesStatus && matchesSearch;
    });
  }, [tasks, filterStatus, searchQuery]);

  // Summary counts
  const counts = useMemo(() => {
    return {
      active: tasks.filter((t) => ACTIVE_STATUSES.includes(t.status)).length,
      approvals: tasks.filter((t) => t.status === 'WAITING_APPROVAL').length,
      completed: tasks.filter((t) => t.status === 'COMPLETED').length,
      failed: tasks.filter((t) => t.status === 'FAILED').length,
    };
  }, [tasks]);

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">Tasks</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Submit, supervise, and inspect multi-agent autonomous execution
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold transition-all shadow-xs"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New Task</span>
        </button>
      </div>

      {/* Summary Counts */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Active', value: counts.active, color: 'text-blue-400' },
          { label: 'Pending Approval', value: counts.approvals, color: 'text-amber-400' },
          { label: 'Completed', value: counts.completed, color: 'text-emerald-400' },
          { label: 'Failed', value: counts.failed, color: 'text-rose-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-slate-900 border border-slate-800 rounded-lg px-4 py-3">
            <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-900 border border-slate-800 p-3 rounded-xl">
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search tasks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="flex items-center space-x-2 w-full sm:w-auto">
          <SlidersHorizontal className="w-4 h-4 text-slate-500" />
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
          >
            <option value="ALL">ALL ({tasks.length})</option>
            <option value="PENDING">PENDING</option>
            <option value="PLANNING">PLANNING</option>
            <option value="EXECUTING">EXECUTING</option>
            <option value="WAITING_APPROVAL">APPROVAL GATE</option>
            <option value="COMPLETED">COMPLETED</option>
            <option value="FAILED">FAILED</option>
            <option value="CANCELLED">CANCELLED</option>
          </select>
        </div>
      </div>

      {/* Task Grid */}
      {filteredTasks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center border border-dashed border-slate-800 rounded-xl">
          <LayoutList className="w-10 h-10 text-slate-700 mb-4" />
          <p className="text-slate-400 font-medium mb-1">
            {tasks.length === 0 ? 'No tasks yet' : 'No tasks match the current filter'}
          </p>
          <p className="text-xs text-slate-600 mb-5">
            {tasks.length === 0
              ? 'Submit an engineering task to start multi-agent execution.'
              : 'Try adjusting your search or status filter.'}
          </p>
          {tasks.length === 0 && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create First Task
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredTasks.map((task) => (
            <TaskCard
              key={task.task_id}
              task={task}
              onSelect={() => onSelectTask(task.task_id)}
              onCancel={() => onCancelTask(task.task_id)}
            />
          ))}
        </div>
      )}

      {/* Create Task Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-xl w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-slate-100">Submit Engineering Task</h3>
                <p className="text-xs text-slate-400">
                  Define objective, workspace constraints, and routing policy
                </p>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-500 hover:text-slate-300 transition-colors text-lg leading-none font-mono"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                  Objective / Instruction Prompt
                </label>
                <textarea
                  rows={4}
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="e.g. Investigate authentication token refresh failure, identify root cause, implement a safe fix, add regression tests, and prepare patch for approval."
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono text-xs"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    Workspace Root
                  </label>
                  <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-300 font-mono">
                    <FolderGit2 className="w-3.5 h-3.5 mr-2 text-slate-500" />
                    <span>workspace/</span>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    Branch Context
                  </label>
                  <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-300 font-mono">
                    <GitBranch className="w-3.5 h-3.5 mr-2 text-slate-500" />
                    <input
                      type="text"
                      value={branch}
                      onChange={(e) => setBranch(e.target.value)}
                      className="bg-transparent text-slate-200 focus:outline-none w-full"
                    />
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    Priority Level
                  </label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
                  >
                    <option value={1}>P1 — Standard</option>
                    <option value={2}>P2 — High</option>
                    <option value={3}>P3 — Urgent / Security Gate</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end space-x-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition-colors font-mono"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50 font-mono"
                >
                  {isSubmitting ? 'Launching Supervisor...' : 'Start Execution'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
