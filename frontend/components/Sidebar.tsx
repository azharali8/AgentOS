'use client';

import React from 'react';
import {
  LayoutDashboard,
  CheckSquare,
  Bot,
  GitFork,
  Brain,
  Activity,
  Award,
  Settings,
  ShieldAlert,
  FileCheck2,
  LogOut,
  User,
  Shield,
} from 'lucide-react';
import { UserProfile, UserRole } from '../types';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  currentUser: UserProfile | null;
  onSignOut: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  currentUser,
  onSignOut,
}) => {
  const userRole: UserRole = currentUser?.role || 'USER';
  const isAdmin = userRole === 'ADMIN';

  const workspaceNav = [
    { id: 'dashboard', label: 'Overview', icon: LayoutDashboard },
    { id: 'tasks', label: 'Tasks', icon: CheckSquare },
    { id: 'workspace', label: 'Workspace', icon: GitFork },
    { id: 'agents', label: 'Agents', icon: Bot },
    { id: 'approvals', label: 'Approvals', icon: FileCheck2 },
  ];

  const intelligenceNav = [
    { id: 'intelligence', label: 'Intelligence', icon: Brain },
    { id: 'evaluations', label: 'Evaluations', icon: Award },
  ];

  const operationsNav = [
    { id: 'observability', label: 'Observability', icon: Activity },
    { id: 'settings', label: 'System Health', icon: Settings },
  ];

  const securityNav = [
    { id: 'security', label: 'Security Center', icon: ShieldAlert, adminOnly: true },
  ];

  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col h-screen select-none">
      {/* Brand Header */}
      <div className="p-5 border-b border-slate-800 flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <span className="h-2.5 w-2.5 bg-emerald-500 rounded-full animate-pulse" />
            <h1 className="font-bold text-sm tracking-wider text-slate-100 uppercase font-mono">
              AgentOS
            </h1>
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5 font-mono">AI Engineering Platform</p>
        </div>
      </div>

      {/* Categorized Navigation */}
      <nav className="flex-1 px-3 py-3 space-y-4 overflow-y-auto font-sans text-xs">
        {/* Workspace Group */}
        <div className="space-y-1">
          <span className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Workspace
          </span>
          {workspaceNav.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center px-3 py-2 rounded-md font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`}
              >
                <Icon className="w-4 h-4 mr-2.5" />
                {item.label}
              </button>
            );
          })}
        </div>

        {/* Intelligence Group */}
        <div className="space-y-1">
          <span className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Intelligence
          </span>
          {intelligenceNav.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center px-3 py-2 rounded-md font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`}
              >
                <Icon className="w-4 h-4 mr-2.5" />
                {item.label}
              </button>
            );
          })}
        </div>

        {/* Operations Group */}
        <div className="space-y-1">
          <span className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Operations
          </span>
          {operationsNav.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center px-3 py-2 rounded-md font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`}
              >
                <Icon className="w-4 h-4 mr-2.5" />
                {item.label}
              </button>
            );
          })}
        </div>

        {/* Security Group (Admin only) */}
        {isAdmin && (
          <div className="space-y-1">
            <span className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Security
            </span>
            {securityNav.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center px-3 py-2 rounded-md font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                      : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                  }`}
                >
                  <Icon className="w-4 h-4 mr-2.5" />
                  {item.label}
                </button>
              );
            })}
          </div>
        )}
      </nav>

      {/* Authenticated User Area */}
      <div className="p-3.5 border-t border-slate-800 bg-slate-950/60">
        <div className="flex items-center space-x-2.5 mb-2.5">
          <div className="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
            <User className="w-3.5 h-3.5" />
          </div>
          <div className="overflow-hidden">
            <p className="text-xs font-semibold text-slate-200 truncate uppercase">
              {currentUser?.username || 'Authenticated User'}
            </p>
            <p className="text-[10px] text-slate-500 truncate font-mono">
              {currentUser?.email || 'user@agentos.local'}
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-slate-800/60">
          <div className="flex items-center space-x-1.5 font-mono text-[10px]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-emerald-400 font-bold uppercase">{userRole}</span>
          </div>

          <button
            onClick={onSignOut}
            className="flex items-center space-x-1 text-[11px] font-mono text-slate-400 hover:text-rose-400 transition-colors"
            title="Sign out"
          >
            <LogOut className="w-3 h-3" />
            <span>Sign out</span>
          </button>
        </div>
      </div>
    </aside>
  );
};
