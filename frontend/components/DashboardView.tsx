'use client';

import React, { useState } from 'react';
import {
  Sparkles,
  Bot,
  Plus,
  GitBranch,
  Play,
  FolderGit2,
  ChevronRight,
} from 'lucide-react';
import { Task, AgentDefinition, UserProfile } from '../types';
import { AgentOSClient } from '../lib/api';
import { VoiceControl } from './voice/VoiceControl';

interface DashboardViewProps {
  client: AgentOSClient;
  tasks: Task[];
  agents: AgentDefinition[];
  currentUser: UserProfile | null;
  onRefresh: () => void;
  onSelectTask: (taskId: string) => void;
  onNewTaskClick: () => void;
  onDirectCreateTask?: (instruction: string, priority: number) => Promise<void>;
  onNavigateTab?: (tab: string) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  client,
  tasks,
  currentUser,
  onSelectTask,
  onNewTaskClick,
  onDirectCreateTask,
  onNavigateTab,
}) => {
  const [instruction, setInstruction] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);


  // Filter out benchmark/harness tasks for user workspace
  const userTasks = tasks.filter(
    (t) =>
      !t.instruction.toLowerCase().includes('benchmark') &&
      !t.instruction.toLowerCase().includes('test harness')
  );

  const activeTasks = userTasks.filter((t) =>
    ['PENDING', 'PLANNING', 'RUNNING', 'EXECUTING', 'WAITING_APPROVAL'].includes(t.status)
  );

  const greetingName = currentUser?.username?.split('@')[0] || '';

  const handleComposeSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!instruction.trim() || isSubmitting) return;
    setIsSubmitting(true);
    try {
      if (onDirectCreateTask) {
        await onDirectCreateTask(instruction.trim(), 1);
        setInstruction('');
      } else {
        onNewTaskClick();
      }
    } finally {
      setIsSubmitting(false);
    }
  };


  return (
    <div className="max-w-4xl mx-auto space-y-8 pt-4 pb-16">
      {/* Hero Greeting */}
      <div className="space-y-1">
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">
          Good morning{greetingName ? `, ${greetingName}` : ''}
        </h1>
        <p className="text-slate-500 text-sm font-normal">
          What are we building today?
        </p>
      </div>

      {/* Large AI Task Composer Box (Matching Page 1) */}
      <div className="bg-white rounded-2xl border border-slate-200/90 shadow-[0_2px_12px_rgba(0,0,0,0.03)] p-4 space-y-4">
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleComposeSubmit();
            }
          }}
          placeholder='e.g. "Fix authentication refresh-token handling" (Press Enter to run)'
          rows={4}
          className="w-full text-sm text-slate-900 placeholder:text-slate-400 bg-transparent border-none resize-none focus:outline-none focus:ring-0 leading-relaxed font-sans"
        />

        <div className="flex flex-col sm:flex-row items-center justify-between pt-2 gap-3 border-t border-slate-100">
          {/* Voice Input Integration */}
          <span className="text-xs text-slate-500">Speak using Voice above, or type an instruction for the Supervisor.</span>

          <div className="flex items-center space-x-2.5">
            <button
              type="button"
              onClick={() => handleComposeSubmit()}
              disabled={!instruction.trim() || isSubmitting}
              className="flex items-center space-x-1.5 px-3.5 py-2 bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 rounded-xl text-xs font-medium transition-colors"
            >
              <Bot className="w-3.5 h-3.5 text-slate-600" />
              <span>Plan with Supervisor</span>
            </button>

            <button
              type="button"
              onClick={() => handleComposeSubmit()}
              disabled={!instruction.trim() || isSubmitting}
              className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold transition-all shadow-xs"
            >
              <Sparkles className="w-3.5 h-3.5 fill-white" />
              <span>Run Autonomously</span>
            </button>
          </div>
        </div>
      </div>

      {/* Action Buttons Row (Page 1) */}
      <div className="flex flex-wrap items-center gap-2.5">
        <button
          onClick={onNewTaskClick}
          className="flex items-center space-x-1.5 px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-700 shadow-2xs transition-colors"
        >
          <Plus className="w-3.5 h-3.5 text-slate-500" />
          <span>+ New Task</span>
        </button>

        <button
          onClick={() => onNavigateTab ? onNavigateTab('tasks') : onSelectTask(tasks[0]?.task_id || '')}
          className="flex items-center space-x-1.5 px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-700 shadow-2xs transition-colors"
        >
          <GitBranch className="w-3.5 h-3.5 text-slate-500" />
          <span>Review Changes</span>
        </button>

        <button
          onClick={() => onNavigateTab ? onNavigateTab('activity') : null}
          className="flex items-center space-x-1.5 px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-700 shadow-2xs transition-colors"
        >
          <Play className="w-3.5 h-3.5 text-slate-500" />
          <span>Run Tests</span>
        </button>

        <button
          onClick={() => onNavigateTab ? onNavigateTab('repository') : null}
          className="flex items-center space-x-1.5 px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-700 shadow-2xs transition-colors"
        >
          <FolderGit2 className="w-3.5 h-3.5 text-slate-500" />
          <span>Open Repository</span>
        </button>
      </div>

      {/* Active Tasks Section (Page 1) */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Active Tasks</h2>
          <button
            onClick={() => onNavigateTab ? onNavigateTab('tasks') : onNewTaskClick()}
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center space-x-0.5"
          >
            <span>View all</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {activeTasks.length === 0 ? (
          <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-8 text-center text-slate-400 text-xs">
            No active engineering tasks. Enter a prompt above to start.
          </div>
        ) : (
          <div className="space-y-2">
            {activeTasks.slice(0, 5).map((task) => (
              <div
                key={task.task_id}
                onClick={() => onSelectTask(task.task_id)}
                className="bg-white hover:bg-slate-50 border border-slate-200/90 rounded-xl p-3.5 flex items-center justify-between cursor-pointer transition-all shadow-2xs"
              >
                <div className="flex items-center space-x-3 truncate">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      task.status === 'WAITING_APPROVAL'
                        ? 'bg-amber-500'
                        : task.status === 'EXECUTING'
                        ? 'bg-indigo-600'
                        : 'bg-emerald-500'
                    }`}
                  />
                  <span className="text-xs font-medium text-slate-800 truncate">
                    {task.instruction}
                  </span>
                </div>
                <div className="flex items-center space-x-2 text-slate-400">
                  <span className="text-[11px] font-mono">{task.status}</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
