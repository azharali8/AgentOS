'use client';

import React, { useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Terminal,
  Activity,
  AlertCircle,
  Code2,
  FileCheck2,
  Shield,
  Layers,
  ChevronRight,
  RefreshCw,
  FileText,
} from 'lucide-react';
import { Task, TaskEvent } from '../types';

interface TaskExecutionViewProps {
  task: Task;
  events: TaskEvent[];
  isStreaming: boolean;
  onBack: () => void;
  onResolveApproval?: (approvalId: string, approved: boolean) => Promise<void>;
}

export const TaskExecutionView: React.FC<TaskExecutionViewProps> = ({
  task,
  events,
  isStreaming,
  onBack,
  onResolveApproval,
}) => {
  const [selectedEvent, setSelectedEvent] = useState<TaskEvent | null>(null);
  const [resolving, setResolving] = useState(false);

  // Group and map events
  const toolEvents = events.filter((e) =>
    ['TOOL_INVOCATION', 'TOOL_RESULT', 'SUBTASK_COMPLETED', 'SUBTASK_CREATED'].includes(e.event_type)
  );

  const approvalEvents = events.filter((e) =>
    ['APPROVAL_REQUIRED', 'APPROVAL_RESOLVED', 'HUMAN_APPROVAL_REQUESTED'].includes(e.event_type)
  );

  const handleApprovalAction = async (approved: boolean) => {
    if (!task.approval_id || !onResolveApproval) return;
    setResolving(true);
    try {
      await onResolveApproval(task.approval_id, approved);
    } finally {
      setResolving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header Bar */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center space-x-2 text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Tasks</span>
        </button>

        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2 text-xs font-mono bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-md">
            <span className={`w-2 h-2 rounded-full ${isStreaming ? 'bg-emerald-500 animate-pulse' : 'bg-slate-500'}`} />
            <span className="text-slate-300">{isStreaming ? 'STREAMING ACTIVE' : 'STREAM IDLE'}</span>
          </div>

          <span
            className={`text-xs px-3 py-1 rounded font-mono font-bold ${
              task.status === 'COMPLETED'
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                : task.status === 'FAILED'
                ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                : task.status === 'WAITING_APPROVAL'
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse'
                : 'bg-blue-500/10 text-blue-400 border border-blue-500/30'
            }`}
          >
            {task.status}
          </span>
        </div>
      </div>

      {/* Task Overview Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Engineering Objective</span>
          <span className="text-xs text-slate-500 font-mono">ID: {task.task_id}</span>
        </div>
        <p className="text-sm font-medium text-slate-100 font-mono">{task.instruction}</p>

        {task.result_summary && (
          <div className="p-3.5 bg-slate-950/80 rounded-lg border border-slate-800 mt-2">
            <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider block mb-1">
              Final Supervisor Response & Evidence
            </span>
            <p className="text-xs text-slate-300 font-mono whitespace-pre-wrap">{task.result_summary}</p>
          </div>
        )}

        {task.error && (
          <div className="p-3.5 bg-rose-950/40 rounded-lg border border-rose-800/40 mt-2 flex items-start space-x-2">
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <span className="text-xs font-semibold text-rose-300 uppercase tracking-wider block">
                Execution Error / Halt
              </span>
              <p className="text-xs text-rose-300 font-mono mt-0.5">{task.error}</p>
            </div>
          </div>
        )}

        {/* Human Approval Banner if waiting */}
        {task.status === 'WAITING_APPROVAL' && (
          <div className="p-4 bg-amber-950/40 border border-amber-500/40 rounded-lg mt-3 flex items-center justify-between">
            <div className="flex items-start space-x-3">
              <Shield className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="text-xs font-bold text-amber-200 uppercase tracking-wider">
                  Human Approval Gate Triggered
                </h4>
                <p className="text-xs text-amber-300/80 font-mono mt-0.5">
                  Supervisor paused execution before applying high-risk patch / modifications.
                </p>
                {task.approval_id && (
                  <p className="text-[11px] text-amber-400 font-mono mt-1">Approval ID: {task.approval_id}</p>
                )}
              </div>
            </div>
            {onResolveApproval && task.approval_id && (
              <div className="flex items-center space-x-2">
                <button
                  disabled={resolving}
                  onClick={() => handleApprovalAction(false)}
                  className="px-3 py-1.5 bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 rounded text-xs font-mono transition-colors"
                >
                  Reject
                </button>
                <button
                  disabled={resolving}
                  onClick={() => handleApprovalAction(true)}
                  className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-mono font-bold transition-colors shadow-sm"
                >
                  {resolving ? 'Authorizing...' : 'Approve & Resume'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Main Console Grid: Dynamic Event Timeline + Tool Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Dynamic Chronological Timeline */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col h-[520px]">
          <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-2">
            <h3 className="font-semibold text-slate-200 flex items-center text-xs uppercase tracking-wider">
              <Terminal className="w-4 h-4 mr-2 text-blue-400" />
              Dynamic Execution Timeline ({events.length} Events)
            </h3>
            <span className="text-[11px] text-slate-400 font-mono">Append-Only Audit</span>
          </div>

          <div className="flex-1 bg-slate-950 border border-slate-800/80 rounded-lg p-3 font-mono text-xs overflow-y-auto space-y-2">
            {events.length === 0 ? (
              <div className="text-slate-600 text-center py-16">
                <Clock className="w-6 h-6 mx-auto mb-2 opacity-50" />
                <p>Waiting for live Supervisor events...</p>
              </div>
            ) : (
              events.map((ev, idx) => {
                const isSelected = selectedEvent?.event_id === ev.event_id;
                return (
                  <div
                    key={ev.event_id || idx}
                    onClick={() => setSelectedEvent(ev)}
                    className={`flex items-start justify-between p-2 rounded cursor-pointer transition-colors border ${
                      isSelected
                        ? 'bg-blue-950/40 border-blue-500/50'
                        : 'bg-slate-900/40 border-slate-800/60 hover:bg-slate-800/50'
                    }`}
                  >
                    <div className="flex items-start space-x-2 truncate">
                      <span className="text-slate-500 text-[10px] whitespace-nowrap pt-0.5">
                        {new Date(ev.timestamp).toLocaleTimeString()}
                      </span>
                      <span
                        className={`text-[11px] font-bold whitespace-nowrap ${
                          ev.event_type.includes('COMPLETED')
                            ? 'text-emerald-400'
                            : ev.event_type.includes('FAILED') || ev.event_type.includes('ERROR')
                            ? 'text-rose-400'
                            : ev.event_type.includes('APPROVAL')
                            ? 'text-amber-400'
                            : 'text-blue-400'
                        }`}
                      >
                        [{ev.event_type}]
                      </span>
                      <span className="text-slate-300 truncate text-[11px]">
                        {ev.payload?.description || ev.payload?.instruction || ev.payload?.agent || JSON.stringify(ev.payload || {})}
                      </span>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-600 flex-shrink-0 ml-2" />
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Structured Event / Tool Call / Patch Inspector */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col h-[520px]">
          <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-2">
            <h3 className="font-semibold text-slate-200 flex items-center text-xs uppercase tracking-wider">
              <Code2 className="w-4 h-4 mr-2 text-emerald-400" />
              Event & Tool Call Inspector
            </h3>
            {selectedEvent && (
              <span className="text-[10px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                {selectedEvent.event_type}
              </span>
            )}
          </div>

          <div className="flex-1 bg-slate-950 border border-slate-800/80 rounded-lg p-3 font-mono text-xs overflow-y-auto">
            {selectedEvent ? (
              <div className="space-y-3">
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">Event Timestamp</span>
                  <p className="text-slate-300">{new Date(selectedEvent.timestamp).toISOString()}</p>
                </div>

                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">Task Identifier</span>
                  <p className="text-slate-400">{selectedEvent.task_id}</p>
                </div>

                {selectedEvent.step_id && (
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-500 block">Step / Subtask ID</span>
                    <p className="text-slate-400">{selectedEvent.step_id}</p>
                  </div>
                )}

                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">
                    Redacted Payload & Arguments
                  </span>
                  <pre className="bg-slate-900 border border-slate-800 p-2.5 rounded text-[11px] text-slate-300 overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(selectedEvent.payload || {}, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="text-slate-600 text-center py-20">
                <FileText className="w-6 h-6 mx-auto mb-2 opacity-50" />
                <p>Click any event in the timeline to inspect arguments, tool execution, and output.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
