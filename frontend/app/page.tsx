'use client';

import React, { useState, useEffect } from 'react';
import { Sidebar } from '../components/Sidebar';
import { LoginView } from '../components/auth/LoginView';
import { DashboardView } from '../components/DashboardView';
import { TaskCenterView } from '../components/TaskCenterView';
import { TaskExecutionView } from '../components/TaskExecutionView';
import { AgentCenterView } from '../components/AgentCenterView';
import { EvaluationCenterView } from '../components/EvaluationCenterView';
import { WorkspaceView } from '../components/workspace/WorkspaceView';
import { ApprovalCenterView } from '../components/approvals/ApprovalCenterView';
import { ObservabilityView } from '../components/observability/ObservabilityView';
import { SecurityCenterView } from '../components/security/SecurityCenterView';
import { SystemHealthView } from '../components/system/SystemHealthView';
import { AgentOSClient } from '../lib/api';
import { Task, AgentDefinition, UserProfile, UserRole, ModelsStatusResponse } from '../types';
import { useTaskEventStream } from '../hooks/useTaskEventStream';
import {
  Search,
  GitBranch,
  Bell,
  Sparkles,
  Layers,
  ChevronDown,
  CheckCircle2,
  FolderGit2,
  User,
} from 'lucide-react';

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [activeTab, setActiveTab] = useState('workspace');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [modelsStatus, setModelsStatus] = useState<ModelsStatusResponse | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [benchmarks, setBenchmarks] = useState<any | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Initialize with session token from localStorage if present
  useEffect(() => {
    const savedToken = localStorage.getItem('agentos_token');
    const savedUser = localStorage.getItem('agentos_user');
    if (savedToken && savedUser) {
      try {
        setToken(savedToken);
        setCurrentUser(JSON.parse(savedUser));
      } catch {}
    }
  }, []);

  const client = new AgentOSClient(token || undefined);

  const { events: streamEvents, isConnected: isStreaming } = useTaskEventStream(selectedTaskId);

  const loadData = async () => {
    if (!token) return;
    try {
      const [fetchedTasks, fetchedAgents, fetchedModels] = await Promise.all([
        client.listTasks(50),
        client.listAgents(),
        client.getModels().catch(() => null),
      ]);
      setTasks(fetchedTasks);
      setAgents(fetchedAgents);
      setModelsStatus(fetchedModels);
    } catch (err) {
      console.error('Failed to load AgentOS telemetry:', err);
    }
  };

  useEffect(() => {
    if (token) {
      loadData();
      const interval = setInterval(loadData, 5000);
      return () => clearInterval(interval);
    }
  }, [token]);

  const handleLoginSuccess = (newToken: string, user: UserProfile) => {
    const normalizedUser: UserProfile = {
      ...user,
      role: (user.role?.toUpperCase() ?? 'USER') as UserRole,
    };
    setToken(newToken);
    setCurrentUser(normalizedUser);
    localStorage.setItem('agentos_token', newToken);
    localStorage.setItem('agentos_user', JSON.stringify(normalizedUser));
  };

  const handleSignOut = async () => {
    if (client) {
      await client.logout().catch(() => {});
    }
    setToken(null);
    setCurrentUser(null);
    localStorage.removeItem('agentos_token');
    localStorage.removeItem('agentos_user');
  };

  const handleCreateTask = async (
    instruction: string,
    priority: number,
    options?: { requested_agent?: string; execution_mode?: string }
  ) => {
    const newTask = await client.createTask(instruction, priority, options);
    await loadData();
    setSelectedTaskId(newTask.task_id);
    setActiveTab('execution');
  };

  const handleCancelTask = async (taskId: string) => {
    await client.cancelTask(taskId);
    await loadData();
  };

  const handleResolveApproval = async (approvalId: string, approved: boolean) => {
    await client.resolveApproval(approvalId, approved);
    await loadData();
  };

  const handleInvokeAgent = async (agentId: string, instruction: string) => {
    return client.invokeAgent(agentId, instruction);
  };

  const handleRunBenchmarks = async () => {
    setIsEvaluating(true);
    try {
      const res = await client.getEvaluations();
      setBenchmarks(res);
    } catch (err) {
      console.error('Failed to execute benchmark battery:', err);
    } finally {
      setIsEvaluating(false);
    }
  };

  // If not authenticated, render Login Gate
  if (!token || !currentUser) {
    return <LoginView onLoginSuccess={handleLoginSuccess} />;
  }

  const selectedTask = tasks.find((t) => t.task_id === selectedTaskId);
  const userRole: UserRole = currentUser.role;

  return (
    <div className="flex h-screen bg-[#f8fafc] overflow-hidden text-slate-900 font-sans">
      {/* Left Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={(tab) => {
          if (tab !== 'execution') setSelectedTaskId(null);
          setActiveTab(tab);
        }}
        currentUser={currentUser}
        onSignOut={handleSignOut}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top Header Bar (Matching PDF Pages 1-9) */}
        <header className="h-14 bg-white border-b border-slate-200/90 px-6 flex items-center justify-between z-10 shrink-0 select-none">
          {/* Breadcrumb / Workspace Context */}
          <div className="flex items-center space-x-2 text-xs">
            <span className="font-semibold text-slate-700">AgentOS</span>
            <span className="text-slate-400">&gt;</span>
            <span className="font-semibold text-slate-700 capitalize">
              {activeTab === 'execution' ? 'Task Execution' : activeTab}
            </span>
          </div>

          {/* Global Search & System Status */}
          <div className="flex items-center space-x-3">
            {/* Search Input with ⌘K */}
            <div className="relative hidden md:flex items-center">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3" />
              <input
                type="text"
                placeholder="Search files, tasks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-56 bg-slate-50 border border-slate-200 rounded-xl pl-8 pr-9 py-1 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
              <span className="absolute right-2.5 text-[10px] text-slate-400 font-mono">⌘K</span>
            </div>

            {/* Active agents pill — real count from backend */}
            {agents.length > 0 && (
              <div className="flex items-center space-x-1.5 px-2.5 py-1 bg-indigo-50/80 border border-indigo-100 text-indigo-700 rounded-xl text-xs font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
                <span>{agents.length} agent{agents.length !== 1 ? 's' : ''} available</span>
              </div>
            )}

            {/* Current View Pill */}
            <span className="px-2.5 py-1 bg-slate-100 text-slate-700 rounded-xl text-xs font-medium capitalize">
              {activeTab === 'execution' ? 'Tasks' : activeTab}
            </span>

            {/* Bell Notifications */}
            <button
              onClick={() => setActiveTab('artifacts')}
              className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-50 rounded-xl transition-colors"
              title="Notifications"
            >
              <Bell className="w-4 h-4" />
            </button>

            {/* User Profile Avatar Icon */}
            <button
              onClick={handleSignOut}
              title={`Signed in as ${currentUser?.username ?? 'User'} · Click to sign out`}
              className="w-7 h-7 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shadow-xs hover:bg-indigo-700 transition-colors"
            >
              <User className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Viewport Scrollable Area */}
        <main className="flex-1 overflow-y-auto p-8 bg-grid-pattern">
          {activeTab === 'workspace' && (
            <DashboardView
              tasks={tasks}
              agents={agents}
              currentUser={currentUser}
              onRefresh={loadData}
              onSelectTask={(id) => {
                setSelectedTaskId(id);
                setActiveTab('execution');
              }}
              onNewTaskClick={() => setActiveTab('tasks')}
              onDirectCreateTask={handleCreateTask}
              onNavigateTab={(tab) => setActiveTab(tab)}
            />
          )}

          {activeTab === 'repository' && <WorkspaceView client={client} />}

          {activeTab === 'tasks' && (
            <TaskCenterView
              tasks={tasks}
              agents={agents}
              onCreateTask={handleCreateTask}
              onSelectTask={(id) => {
                setSelectedTaskId(id);
                setActiveTab('execution');
              }}
              onCancelTask={handleCancelTask}
            />
          )}

          {activeTab === 'execution' && (
            selectedTask ? (
              <TaskExecutionView
                task={selectedTask}
                events={streamEvents}
                isStreaming={isStreaming}
                onBack={() => {
                  setSelectedTaskId(null);
                  setActiveTab('tasks');
                }}
                onResolveApproval={handleResolveApproval}
              />
            ) : (
              <div className="max-w-2xl mx-auto py-16 text-center space-y-4 bg-white rounded-3xl border border-slate-200/90 p-8 shadow-2xs">
                <p className="text-sm font-semibold text-slate-700">No task selected for execution.</p>
                <button
                  onClick={() => setActiveTab('tasks')}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold"
                >
                  Go to Tasks
                </button>
              </div>
            )
          )}

          {activeTab === 'agents' && (
            <AgentCenterView
              agents={agents}
              tasks={tasks}
              userRole={userRole}
              onInvokeAgent={handleInvokeAgent}
            />
          )}

          {activeTab === 'artifacts' && (
            <ApprovalCenterView client={client} userRole={userRole} />
          )}

          {activeTab === 'activity' && (
            <EvaluationCenterView client={client} />
          )}

          {activeTab === 'operations' && <ObservabilityView client={client} />}

          {activeTab === 'settings' && <SystemHealthView client={client} />}
        </main>
      </div>
    </div>
  );
}
