'use client';

import React, { useState } from 'react';
import {
  LayoutGrid,
  GitBranch,
  CheckSquare,
  Bot,
  Box,
  Activity,
  Layers,
  Settings,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from 'lucide-react';
import { UserProfile } from '../types';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  currentUser: UserProfile | null;
  onSignOut: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const primaryNav = [
    { id: 'workspace', label: 'Workspace', icon: LayoutGrid },
    { id: 'repository', label: 'Repository', icon: GitBranch },
    { id: 'tasks', label: 'Tasks', icon: CheckSquare },
    { id: 'artifacts', label: 'Approvals', icon: Box },
    { id: 'activity', label: 'Activity', icon: Activity },
  ];

  const secondaryNav = [
    { id: 'operations', label: 'Operations', icon: Layers },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside
      className={`${
        isCollapsed ? 'w-[4.5rem]' : 'w-56'
      } bg-white border-r border-slate-200/90 flex flex-col h-screen select-none transition-all duration-200 relative z-20 shrink-0`}
    >
      {/* Brand Header */}
      <div className="h-16 px-4 flex items-center space-x-2.5">
        <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-xs">
          <Sparkles className="w-4 h-4 fill-white" />
        </div>
        {!isCollapsed && (
          <span className="font-bold text-base text-slate-900 font-sans tracking-tight">
            AgentOS
          </span>
        )}
      </div>

      {/* Primary Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
        {primaryNav.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id || (activeTab === 'execution' && item.id === 'tasks');
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              title={isCollapsed ? item.label : undefined}
              className={`w-full flex items-center ${
                isCollapsed ? 'justify-center px-0 py-2' : 'px-3 py-2'
              } rounded-xl text-[13px] font-medium transition-all ${
                isActive
                  ? 'bg-indigo-50/90 text-indigo-600 font-semibold'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-600' : 'text-slate-500'} ${!isCollapsed ? 'mr-3' : ''}`} />
              {!isCollapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Secondary Navigation & Collapse */}
      <div className="p-3 space-y-1 border-t border-slate-100">
        {secondaryNav.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              title={isCollapsed ? item.label : undefined}
              className={`w-full flex items-center ${
                isCollapsed ? 'justify-center px-0 py-2' : 'px-3 py-2'
              } rounded-xl text-[13px] font-medium transition-all ${
                isActive
                  ? 'bg-indigo-50/90 text-indigo-600 font-semibold'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-600' : 'text-slate-500'} ${!isCollapsed ? 'mr-3' : ''}`} />
              {!isCollapsed && <span>{item.label}</span>}
            </button>
          );
        })}

        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className={`w-full flex items-center ${
            isCollapsed ? 'justify-center px-0 py-2' : 'px-3 py-2'
          } rounded-xl text-[13px] font-medium text-slate-500 hover:text-slate-900 hover:bg-slate-50 transition-all`}
        >
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <>
              <ChevronLeft className="w-4 h-4 mr-3" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
};
