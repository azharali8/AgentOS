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

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [modelsStatus, setModelsStatus] = useState<ModelsStatusResponse | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [benchmarks, setBenchmarks] = useState<any | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);

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
    // Normalize role to uppercase to match frontend UserRole type
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
    <div className="flex h-screen bg-slate-950 overflow-hidden text-slate-100 font-sans">
      {/* Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={(tab) => {
          if (tab !== 'execution') setSelectedTaskId(null);
          setActiveTab(tab);
        }}
        currentUser={currentUser}
        onSignOut={handleSignOut}
      />

      {/* Main Viewport */}
      <main className="flex-1 overflow-y-auto p-8">
        {activeTab === 'dashboard' && (
          <DashboardView
            tasks={tasks}
            agents={agents}
            currentUser={currentUser}
            modelsStatus={modelsStatus}
            onRefresh={loadData}
            onSelectTask={(id) => {
              setSelectedTaskId(id);
              setActiveTab('execution');
            }}
            onNewTaskClick={() => setActiveTab('tasks')}
          />
        )}

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

        {activeTab === 'execution' && selectedTask && (
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
        )}

        {activeTab === 'workspace' && <WorkspaceView client={client} />}

        {activeTab === 'approvals' && (
          <ApprovalCenterView client={client} userRole={userRole} />
        )}

        {activeTab === 'agents' && (
          <AgentCenterView
            agents={agents}
            tasks={tasks}
            userRole={userRole}
            onInvokeAgent={handleInvokeAgent}
          />
        )}

        {activeTab === 'observability' && <ObservabilityView client={client} />}

        {activeTab === 'evaluations' && (
          <EvaluationCenterView
            benchmarks={benchmarks}
            onRunBenchmarks={handleRunBenchmarks}
            isLoading={isEvaluating}
          />
        )}

        {activeTab === 'security' && <SecurityCenterView userRole={userRole} />}

        {activeTab === 'settings' && <SystemHealthView client={client} />}
      </main>
    </div>
  );
}
