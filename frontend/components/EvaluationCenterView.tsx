'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  Activity,
  Sparkles,
  Layers,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { AgentOSClient } from '../lib/api';
import { Task, TaskEvent } from '../types';

interface EvaluationCenterViewProps {
  client?: AgentOSClient;
}

interface ActivityEntry {
  time: string;
  rawTimestamp: string;
  agent: string;
  agentBg: string;
  iconColor: string;
  icon: React.ElementType;
  title: string;
  details: string;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '—';
  }
}

function taskStatusIcon(status: string): React.ElementType {
  switch (status) {
    case 'COMPLETED': return CheckCircle2;
    case 'FAILED': return XCircle;
    case 'RUNNING':
    case 'EXECUTING': return Activity;
    case 'WAITING_APPROVAL': return AlertCircle;
    default: return Sparkles;
  }
}

function taskStatusColor(status: string): string {
  switch (status) {
    case 'COMPLETED': return 'bg-emerald-500 text-white';
    case 'FAILED': return 'bg-rose-500 text-white';
    case 'RUNNING':
    case 'EXECUTING': return 'bg-blue-500 text-white';
    case 'WAITING_APPROVAL': return 'bg-amber-500 text-white';
    default: return 'bg-indigo-500 text-white';
  }
}

function taskAgentBg(status: string): string {
  switch (status) {
    case 'COMPLETED': return 'bg-emerald-50 text-emerald-700';
    case 'FAILED': return 'bg-rose-50 text-rose-700';
    case 'RUNNING':
    case 'EXECUTING': return 'bg-blue-50 text-blue-700';
    case 'WAITING_APPROVAL': return 'bg-amber-50 text-amber-700';
    default: return 'bg-indigo-50 text-indigo-700';
  }
}

function eventToEntry(event: TaskEvent): ActivityEntry {
  const eventType = event.event_type || 'EVENT';
  const payload = event.payload || {};

  let agent = payload.agent || eventType.replace(/_/g, ' ');
  let title = payload.message || payload.description || `${eventType}`;
  let details = payload.details || payload.summary || '';

  // Prettify common event types
  if (eventType === 'TASK_STARTED') { agent = 'Supervisor'; title = 'Task started'; }
  if (eventType === 'TASK_COMPLETED') { agent = 'Supervisor'; title = 'Task completed'; }
  if (eventType === 'TASK_FAILED') { agent = 'Supervisor'; title = 'Task failed'; }
  if (eventType === 'PLAN_CREATED') { agent = 'Supervisor'; title = 'Execution plan created'; }
  if (eventType === 'STEP_STARTED') { agent = payload.agent || 'Agent'; title = `Step started: ${payload.step || ''}`; }
  if (eventType === 'STEP_COMPLETED') { agent = payload.agent || 'Agent'; title = `Step completed: ${payload.step || ''}`; }
  if (eventType === 'TOOL_CALL') { agent = payload.agent || 'Agent'; title = `Tool called: ${payload.tool || ''}`; }
  if (eventType === 'APPROVAL_REQUESTED') { agent = 'Supervisor'; title = 'Human approval requested'; }
  if (eventType === 'APPROVAL_RESOLVED') { agent = 'Supervisor'; title = `Approval ${payload.decision || 'resolved'}`; }

  return {
    time: formatTime(event.timestamp),
    rawTimestamp: event.timestamp,
    agent,
    agentBg: 'bg-indigo-50 text-indigo-700',
    iconColor: 'bg-indigo-500 text-white',
    icon: Layers,
    title,
    details,
  };
}

function taskToEntry(task: Task): ActivityEntry {
  const Icon = taskStatusIcon(task.status);
  const label = task.assigned_agent || 'Supervisor';
  const shortInstruction =
    task.instruction.length > 60
      ? task.instruction.slice(0, 60) + '…'
      : task.instruction;

  return {
    time: formatTime(task.updated_at || task.created_at),
    rawTimestamp: task.updated_at || task.created_at,
    agent: label,
    agentBg: taskAgentBg(task.status),
    iconColor: taskStatusColor(task.status),
    icon: Icon,
    title: shortInstruction,
    details: `Status: ${task.status}${task.result_summary ? ` · ${task.result_summary.slice(0, 60)}` : ''}`,
  };
}

export const EvaluationCenterView: React.FC<EvaluationCenterViewProps> = ({ client }) => {
  const [entries, setEntries] = useState<ActivityEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<string>('');

  const loadActivity = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      // Fetch latest tasks
      const tasks = await client.listTasks(20).catch(() => [] as Task[]);

      if (tasks.length === 0) {
        setEntries([]);
        return;
      }

      // Build task-level entries
      const taskEntries: ActivityEntry[] = tasks.map(taskToEntry);

      // Try to enrich with events from the 3 most recent tasks
      const recentTasks = tasks.slice(0, 3);
      const eventArrays = await Promise.all(
        recentTasks.map((t) =>
          client.getTaskEvents(t.task_id).catch(() => [] as TaskEvent[])
        )
      );

      const allEvents: TaskEvent[] = eventArrays.flat();
      const eventEntries: ActivityEntry[] = allEvents.map(eventToEntry);

      // Merge and sort by timestamp descending
      const combined = [...taskEntries, ...eventEntries].sort(
        (a, b) => new Date(b.rawTimestamp).getTime() - new Date(a.rawTimestamp).getTime()
      );

      // Deduplicate by title+time
      const seen = new Set<string>();
      const deduped = combined.filter((e) => {
        const key = `${e.time}-${e.title}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });

      setEntries(deduped.slice(0, 30));
      setLastRefreshed(new Date().toLocaleTimeString());
    } catch (err) {
      console.error('Failed to load activity:', err);
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    loadActivity();
    const interval = setInterval(loadActivity, 10000);
    return () => clearInterval(interval);
  }, [loadActivity]);

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Activity</h1>
          <p className="text-xs text-slate-500">
            Real-time execution log across all agents and tasks
          </p>
        </div>
        <button
          onClick={loadActivity}
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

      {/* Timeline */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-6 shadow-2xs">
        {!client ? (
          <div className="flex flex-col items-center justify-center py-16 space-y-3">
            <AlertCircle className="w-8 h-8 text-slate-300" />
            <p className="text-sm font-medium text-slate-500">Not connected</p>
            <p className="text-xs text-slate-400">Sign in to view activity</p>
          </div>
        ) : loading && entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 space-y-3">
            <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
            <p className="text-xs text-slate-400">Loading activity…</p>
          </div>
        ) : entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 space-y-3">
            <Clock className="w-8 h-8 text-slate-200" />
            <p className="text-sm font-medium text-slate-500">No activity yet</p>
            <p className="text-xs text-slate-400">
              Create and run a task to see live execution events here.
            </p>
          </div>
        ) : (
          <>
            <div className="relative pl-6 space-y-8 before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-100">
              {entries.map((ev, idx) => {
                const Icon = ev.icon;
                return (
                  <div key={idx} className="relative flex items-start space-x-4">
                    {/* Timeline Icon Node */}
                    <div
                      className={`w-6 h-6 rounded-full ${ev.iconColor} flex items-center justify-center -ml-9 shadow-xs shrink-0 z-10`}
                    >
                      <Icon className="w-3 h-3" />
                    </div>

                    {/* Content */}
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center space-x-2.5">
                        <span className="text-xs font-mono text-slate-400 shrink-0">{ev.time}</span>
                        <h3 className="text-xs font-bold text-slate-900 truncate">{ev.title}</h3>
                      </div>
                      <div className="flex items-center space-x-2 text-xs flex-wrap gap-y-1">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${ev.agentBg}`}>
                          {ev.agent}
                        </span>
                        {ev.details && (
                          <span className="text-slate-500 truncate max-w-xs">{ev.details}</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            {lastRefreshed && (
              <p className="text-[10px] text-slate-400 mt-6 text-right">
                Last refreshed {lastRefreshed}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
};
