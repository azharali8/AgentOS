'use client';

import React, { useState } from 'react';
import {
  ArrowLeft,
  ChevronRight,
  ChevronDown,
  Folder,
  FileCode2,
  Send,
  Bot,
  Play,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Terminal,
} from 'lucide-react';
import { Task, TaskEvent } from '../types';

const eventLabel = (event: TaskEvent): string => {
  const labels: Record<string, string> = {
    TASK_CREATED: 'Request received', TASK_CLASSIFIED: 'Understanding request',
    PLAN_CREATED: 'Planning', SUBTASK_CREATED: 'Work planned', AGENT_SELECTED: 'Work delegated',
    PARALLEL_EXECUTION_STARTED: 'Executing planned work', SUBTASK_COMPLETED: 'Work finished',
    SUBTASK_FAILED: 'Work failed', PATCH_CREATED: 'Changes proposed', PATCH_APPLIED: 'Applying changes',
    TEST_COMPLETED: 'Tests finished', APPROVAL_REQUIRED: 'Waiting for approval',
    APPROVAL_RESOLVED: 'Approval resolved', TASK_COMPLETED: 'Completed', TASK_FAILED: 'Failed',
    REPLAN_TRIGGERED: 'Investigating failure',
  };
  if (event.event_type === 'SUBTASK_STARTED') {
    const stages: Record<string, string> = {RESEARCH: 'Analyzing repository', CODING: 'Implementing changes',
      TESTING: 'Running tests', DEBUGGER: 'Investigating failure', REVIEWER: 'Reviewing changes',
      SECURITY: 'Checking security', DOCUMENTATION: 'Preparing documentation'};
    return stages[String(event.payload?.agent).toUpperCase()] || 'Executing delegated work';
  }
  return labels[event.event_type] || event.event_type.replace(/[_.]/g, ' ').toLowerCase();
};

interface TaskExecutionViewProps {
  task: Task;
  events: TaskEvent[];
  isStreaming: boolean;
  onBack: () => void;
  onResolveApproval?: (approvalId: string, approved: boolean) => Promise<void>;
}

export const TaskExecutionView: React.FC<TaskExecutionViewProps> = ({
  task,
  events = [],
  isStreaming,
  onBack,
  onResolveApproval,
}) => {
  const [activeTab, setActiveTab] = useState<'execution' | 'code' | 'diff' | 'tests' | 'review'>('execution');
  const approvalEvent = [...events].reverse().find(e => e.event_type === 'APPROVAL_REQUIRED');
  const approvalId = approvalEvent?.payload?.approval_id as string | undefined;

  const statusColor =
    task.status === 'COMPLETED'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : task.status === 'WAITING_APPROVAL'
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : task.status === 'FAILED'
      ? 'bg-rose-50 text-rose-700 border-rose-200'
      : 'bg-indigo-50 text-indigo-700 border-indigo-200';

  return (
    <div className="max-w-7xl mx-auto space-y-4 pb-12">
      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2">
        <div className="flex items-center space-x-3">
          <button
            onClick={onBack}
            className="flex items-center space-x-1 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-white border border-slate-200 px-2.5 py-1 rounded-lg transition-colors shadow-2xs"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back</span>
          </button>

          <div className="flex items-center space-x-2">
            <span className="px-2.5 py-0.5 bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-bold rounded-md font-mono">
              #{task.task_id.slice(0, 8)}
            </span>
            <h1 className="text-base font-bold text-slate-900 truncate max-w-lg">
              {task.instruction}
            </h1>
          </div>
        </div>

        <div className="flex items-center space-x-2.5">
          <span className={`px-2.5 py-1 text-[11px] font-bold rounded-lg border ${statusColor}`}>
            {task.status}
          </span>
        </div>
      </div>

      {/* 3-Column IDE Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Left: Task Summary & Meta */}
        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-200/90 p-4 space-y-4 shadow-2xs font-mono text-xs">
          <div className="space-y-2">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block font-sans">
              Task Details
            </span>
            <div className="space-y-2 text-slate-700 font-sans">
              <div>
                <span className="text-slate-400 text-[10px] block">Created At</span>
                <span className="text-xs font-mono">{new Date(task.created_at).toLocaleTimeString()}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Priority</span>
                <span className="text-xs font-mono">P{task.priority || 1}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Coordinated by</span>
                <span className="text-xs font-mono text-indigo-600">Supervisor</span>
              </div>
            </div>
          </div>

          {/* Real Events Count */}
          <div className="pt-3 border-t border-slate-100 space-y-2">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block font-sans">
              Telemetry
            </span>
            <div className="flex flex-wrap gap-1.5 text-[11px]">
              <span className="px-2 py-0.5 bg-slate-100 rounded-md text-slate-700">{events.length} events</span>
              {isStreaming && (
                <span className="px-2 py-0.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-md flex items-center space-x-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
                  <span>Streaming</span>
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Center: Live Execution & Real Terminal Stream (6 cols) */}
        <div className="lg:col-span-6 space-y-3">
          {/* Tabs Row */}
          <div className="flex items-center space-x-1 bg-white p-1 rounded-xl border border-slate-200/90 shadow-2xs overflow-x-auto">
            {[
              { id: 'execution', label: 'Live Trace', badge: `${events.length} events` },
              { id: 'diff', label: 'Result' },
              { id: 'tests', label: 'Tests' },
            ].map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? 'bg-slate-100 text-slate-900 font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded font-mono font-semibold bg-slate-200 text-slate-700">
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Live Trace or Diff Container */}
          <div className="bg-white rounded-2xl border border-slate-200/90 overflow-hidden shadow-2xs min-h-[280px]">
            {activeTab === 'execution' && (
              <div className="p-4 space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100 text-xs">
                  <span className="font-bold text-slate-900">Execution Events</span>
                  <span className="text-slate-400 font-mono text-[11px]">{task.status}</span>
                </div>

                {events.length === 0 ? (
                  <div className="py-12 text-center text-slate-400 text-xs">
                    {isStreaming ? 'Waiting for execution events…' : 'Event stream disconnected; reconnecting…'}
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[340px] overflow-y-auto pr-1">
                    {events.map((ev, i) => (
                      <div key={ev.event_id || i} className="p-3 bg-slate-50 border border-slate-100 rounded-xl space-y-1 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-indigo-700 text-[11px]">{eventLabel(ev)}</span>
                          <span className="text-slate-400 font-mono text-[10px]">{ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''}</span>
                        </div>
                        {ev.event_type === 'SUBTASK_STARTED' && ev.payload?.description && <p>{String(ev.payload.description)}</p>}
                        {(ev.payload?.agent || ev.payload?.agent_type) && (
                          <p className="text-[10px] text-slate-500">{String(ev.payload.agent || ev.payload.agent_type)} · delegated by Supervisor</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === 'diff' && (
              <div className="p-8 text-center text-slate-400 text-xs">
                {task.result_summary ? (
                  <div className="text-left font-mono text-xs text-slate-800 whitespace-pre-wrap">
                    {task.result_summary}
                  </div>
                ) : (
                  'No result recorded for this task yet.'
                )}
              </div>
            )}

            {activeTab === 'tests' && (
              <div className="p-8 text-center text-slate-400 text-xs">
                {events.filter(e => e.event_type === 'TEST_COMPLETED').map(e => (
                  <p key={e.event_id}>{e.payload?.report ? `${e.payload.report.passed_count ?? 0} passed, ${e.payload.report.failed_count ?? 0} failed; exit code ${e.payload.report.exit_code ?? 'unknown'}` : 'Test execution finished; inspect the test artifact for details.'}</p>
                ))}
                {!events.some(e => e.event_type === 'TEST_COMPLETED') && 'No test suite execution recorded for this task yet.'}
              </div>
            )}
          </div>

          {/* Integrated Dark Terminal Stream */}
          <div className="bg-[#0f172a] text-slate-200 rounded-2xl p-3.5 font-mono text-xs space-y-2 shadow-sm">
            <div className="flex items-center space-x-3 text-[11px] text-slate-400 border-b border-slate-800 pb-2">
              <span className="text-white font-bold flex items-center space-x-1.5">
                <Terminal className="w-3.5 h-3.5" />
                <span>Console Logs</span>
              </span>
              {isStreaming && <span className="text-emerald-400 text-[10px]">● live</span>}
            </div>
            <div className="space-y-1 select-text pt-1 text-[11px] max-h-40 overflow-y-auto">
              <p className="text-slate-400">[AgentOS] Task #{task.task_id.slice(0, 8)} status: {task.status}</p>
              {events.map((e, idx) => (
                <p key={idx} className="text-slate-300">
                  <span className="text-indigo-400">&gt;</span> [{e.event_type}] {eventLabel(e)}
                </p>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Supervisor Interaction (3 cols) */}
        <div className="lg:col-span-3 space-y-4">
          <div className="bg-white rounded-2xl border border-slate-200/90 p-4 space-y-3 shadow-2xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <div className="flex items-center space-x-2">
                <Bot className="w-4 h-4 text-indigo-600" />
                <h3 className="text-xs font-bold text-slate-900">Supervisor</h3>
              </div>
              <span className="flex items-center space-x-1 text-[11px] text-indigo-600 font-semibold">
                <span>{task.status}</span>
              </span>
            </div>

            <div className="bg-slate-50 rounded-xl p-3 text-xs text-slate-700 leading-relaxed space-y-1">
              <p>Task #{task.task_id.slice(0, 8)} is in state <strong>{task.status}</strong>.</p>
              {task.error && <p className="text-rose-600 font-mono text-[11px]">{task.error}</p>}
            </div>

            {task.result_summary && <p className="text-xs whitespace-pre-wrap">{task.result_summary}</p>}
            {task.status === 'WAITING_APPROVAL' && approvalId && onResolveApproval && (
              <div className="text-xs space-y-2">
                <p>Review the proposed patch in Approvals before resolving it.</p>
              </div>
            )}
            <p className="text-xs text-slate-500">Use Voice for a follow-up, or create another Supervisor task.</p>
          </div>
        </div>
      </div>
    </div>
  );
};
