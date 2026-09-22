'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { LoginView } from '../components/auth/LoginView';
import { useAuthSession } from '../hooks/useAuthSession';
import { DashboardView } from '../components/DashboardView';
import { SettingsView } from '../components/SettingsView';
import { useWorkspaceSettings } from '../hooks/useWorkspaceSettings';
import { AgentOSClient } from '../lib/api';
import { Task, AgentDefinition, ModelsStatusResponse } from '../types';
import { Sparkles, ArrowLeft } from 'lucide-react';

export default function Home() {
  const { token, user: currentUser, checking, notice, login: handleLoginSuccess, logout: handleSignOut, refresh } = useAuthSession();
  const [activeTab, setActiveTab] = useState<'workspace' | 'settings'>('workspace');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [modelsStatus, setModelsStatus] = useState<ModelsStatusResponse | null>(null);

  // Reset to workspace on token change
  useEffect(() => {
    setTasks([]);
    setAgents([]);
    setModelsStatus(null);
    setActiveTab('workspace');
  }, [token]);

  const client = useMemo(() => new AgentOSClient(token || undefined), [token]);
  const preferences = useWorkspaceSettings(client, !!token);

  const currentToken = useRef(token);
  currentToken.current = token;

  const loadData = async () => {
    if (!token) return;
    try {
      const [fetchedTasks, fetchedAgents, fetchedModels] = await Promise.all([
        client.listTasks(50),
        client.listAgents(),
        client.getModels().catch(() => null),
      ]);
      if (currentToken.current !== token) return;
      setTasks(fetchedTasks);
      setAgents(fetchedAgents);
      setModelsStatus(fetchedModels);
    } catch (err) {
      console.error('Failed to load AgentOS data:', err);
    }
  };

  useEffect(() => {
    if (token) {
      loadData();
      const interval = setInterval(loadData, 5000);
      return () => clearInterval(interval);
    }
  }, [token]);

  // Loading screen
  if (checking) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[#fcfdfd] text-slate-600" role="status" aria-live="polite">
        <div className="text-center">
          <Sparkles className="mx-auto mb-4 h-8 w-8 text-indigo-600 animate-pulse motion-reduce:animate-none" />
          <p className="text-sm font-medium">Opening your workspace…</p>
        </div>
      </main>
    );
  }

  // Login gate
  if (!token || !currentUser) {
    return <LoginView onLoginSuccess={handleLoginSuccess} notice={notice} onRetrySession={refresh} />;
  }

  return (
    <div className="workspace-shell flex h-screen overflow-hidden theme-bg-canvas theme-text-primary font-sans">
      {activeTab === 'workspace' ? (
        <div className="flex-1 h-screen overflow-hidden">
          <DashboardView
            client={client}
            tasks={tasks}
            preferences={preferences}
            agents={agents}
            currentUser={currentUser}
            onRefresh={loadData}
            onSelectTask={() => {}}
            onNewTaskClick={() => {}}
            onDirectCreateTask={async (instruction, priority, options) => {
              await client.createTask(instruction, priority, options);
              await loadData();
            }}
            onNavigateTab={(tab) => {
              if (tab === 'settings') setActiveTab('settings');
            }}
            onOpenSettings={() => setActiveTab('settings')}
            onSignOut={handleSignOut}
          />
        </div>
      ) : (
        <div className="flex-1 h-screen flex flex-col theme-bg-canvas overflow-hidden">
          {/* Settings Minimal Top Header */}
          <header className="h-13 px-6 border-b theme-border theme-bg-surface flex items-center justify-between z-10 shrink-0">
            <button
              onClick={() => setActiveTab('workspace')}
              className="flex items-center space-x-2 text-xs font-semibold theme-text-muted hover:theme-text-primary transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to Workspace</span>
            </button>
            <span className="text-xs font-bold theme-text-primary">AgentOS Settings</span>
          </header>

          <main className="flex-1 overflow-y-auto p-6 md:p-10">
            <SettingsView
              user={currentUser}
              onSignOut={handleSignOut}
              preferences={preferences}
            />
          </main>
        </div>
      )}
    </div>
  );
}
