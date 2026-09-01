'use client';

import React, { useState, useMemo } from 'react';
import { Bot, Sparkles, Code2, CheckCircle2, Shield, Bug, Search } from 'lucide-react';
import { AgentDefinition, UserRole, Task } from '../types';

interface AgentCenterViewProps {
  agents?: AgentDefinition[];
  userRole?: UserRole;
  tasks?: Task[];
  onInvokeAgent?: (agentId: string, instruction: string) => Promise<any>;
}

export const AgentCenterView: React.FC<AgentCenterViewProps> = ({
  agents = [],
  tasks = [],
}) => {
  // Built-in core agents fallback if backend is populating asynchronously
  const defaultAgentCards = [
    {
      agent_type: 'supervisor',
      name: 'Supervisor',
      role: 'Orchestration & Planning',
      status: 'Idle',
      statusColor: 'text-slate-600 bg-slate-100',
      description: 'Awaiting agent results',
      tasks: '47 tasks',
      time: '3h 12m',
      iconBg: 'bg-indigo-600 text-white',
      tools: ['Task Planner', 'DAG Scheduler', 'LLM Router'],
      capabilities: ['Decomposition', 'Replanning', 'Governance'],
    },
    {
      agent_type: 'repo_analyst',
      name: 'Repository Analyst',
      role: 'Codebase Understanding',
      status: 'Complete',
      statusColor: 'text-emerald-700 bg-emerald-50',
      description: 'Analyzed 142 files — 18 affected',
      tasks: '12 tasks',
      time: '2h 48m',
      iconBg: 'bg-indigo-600 text-white',
      tools: ['AST Indexer', 'Symbol Graph', 'ripgrep'],
      capabilities: ['Semantic Code Search', 'Dependency Resolution'],
    },
    {
      agent_type: 'coding',
      name: 'Coding Agent',
      role: 'Code Generation & Modification',
      status: 'Complete',
      statusColor: 'text-emerald-700 bg-emerald-50',
      description: 'Implemented token rotation — 2 files changed',
      tags: ['auth_service.py', 'token_service.py'],
      tasks: '8 tasks',
      time: '1h 55m',
      iconBg: 'bg-emerald-600 text-white',
      tools: ['AST Patch Engine', 'Linter', 'Code Editor'],
      capabilities: ['Code Synthesis', 'Atomic Refactoring'],
    },
    {
      agent_type: 'testing',
      name: 'Testing Agent',
      role: 'Test Execution & Coverage',
      status: 'Working',
      statusColor: 'text-amber-700 bg-amber-50',
      description: 'Running test suite — 5/7 complete',
      isWorking: true,
      tasks: '31 tasks',
      time: '2h 10m',
      iconBg: 'bg-amber-500 text-white',
      tools: ['pytest', 'Coverage.py', 'Test Generator'],
      capabilities: ['Subprocess Runner', 'Regression Suite'],
    },
    {
      agent_type: 'debugger',
      name: 'Debugger',
      role: 'Root Cause Diagnosis',
      status: 'Idle',
      statusColor: 'text-slate-600 bg-slate-100',
      description: 'Ready for trace analysis & failure triage',
      tasks: '19 tasks',
      time: '1h 15m',
      iconBg: 'bg-rose-500 text-white',
      tools: ['Trace Analyzer', 'Memory Profiler', 'Stack Inspector'],
      capabilities: ['Diagnostic Engine', 'Failure Learning'],
    },
    {
      agent_type: 'reviewer',
      name: 'Review Agent',
      role: 'Code Quality & Security Gate',
      status: 'Complete',
      statusColor: 'text-emerald-700 bg-emerald-50',
      description: '0 critical vulnerabilities detected',
      tasks: '26 tasks',
      time: '2h 05m',
      iconBg: 'bg-blue-600 text-white',
      tools: ['SAST Scanner', 'Diff Analyzer', 'Policy Engine'],
      capabilities: ['Security Review', 'Risk Assessment'],
    },
  ];

  // Map backend registered agents dynamically into visual cards
  const displayAgents = useMemo(() => {
    if (!agents || agents.length === 0) {
      return defaultAgentCards;
    }

    // Merge registered backend agents with PDF aesthetic metadata
    return agents.map((agent) => {
      const match = defaultAgentCards.find(
        (d) =>
          d.agent_type.toLowerCase() === agent.agent_type.toLowerCase() ||
          d.name.toLowerCase() === agent.name.toLowerCase()
      );

      const agentTaskCount = tasks.filter(
        (t) => (t as any).agent === agent.name || (t as any).requested_agent === agent.agent_type
      ).length;

      return {
        agent_type: agent.agent_type,
        name: agent.name.replace(/_/g, ' '),
        role: match?.role || agent.description || 'Specialized Domain Agent',
        status: match?.status || 'Active',
        statusColor: match?.statusColor || 'text-indigo-700 bg-indigo-50',
        description: agent.description || match?.description || 'Autonomous engineering agent',
        tags: match?.tags,
        tasks: `${agentTaskCount} task${agentTaskCount !== 1 ? 's' : ''}`,
        time: `${agent.max_execution_time}s TTL`,
        iconBg: match?.iconBg || 'bg-indigo-600 text-white',
        tools: match?.tools || ['AST Parser', 'Python Sandbox', 'Event Logger'],
        capabilities: agent.capabilities && agent.capabilities.length > 0 ? agent.capabilities : (match?.capabilities || ['General Execution']),
        isWorking: match?.isWorking,
      };
    });
  }, [agents, tasks]);

  const [selectedAgentName, setSelectedAgentName] = useState<string>(
    displayAgents[3]?.name || displayAgents[0]?.name || 'Testing Agent'
  );

  const selectedAgent = displayAgents.find((a) => a.name === selectedAgentName) || displayAgents[0];

  return (
    <div className="max-w-6xl mx-auto flex flex-col lg:flex-row gap-6 pb-12 items-start">
      {/* Main Agent Grid (Matching Page 4 Layout with Dynamic Scale) */}
      <div className="flex-1 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Agent System</h1>
            <p className="text-xs text-slate-500 mt-0.5 font-mono">
              {displayAgents.length} agents registered & available in orchestrator
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {displayAgents.map((agent) => {
            const isSelected = selectedAgent?.name === agent.name;
            return (
              <div
                key={agent.name}
                onClick={() => setSelectedAgentName(agent.name)}
                className={`bg-white rounded-2xl border p-4.5 space-y-3 cursor-pointer transition-all shadow-2xs ${
                  isSelected ? 'border-indigo-300 ring-2 ring-indigo-50' : 'border-slate-200/90 hover:border-slate-300'
                }`}
              >
                {/* Card Header */}
                <div className="flex items-start justify-between">
                  <div className="flex items-center space-x-2.5">
                    <div className={`w-8 h-8 rounded-xl ${agent.iconBg} flex items-center justify-center shrink-0 shadow-xs`}>
                      <Bot className="w-4 h-4" />
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-slate-900 capitalize">{agent.name}</h3>
                      <p className="text-[11px] text-slate-400 capitalize">{agent.role}</p>
                    </div>
                  </div>

                  <span className={`text-[10px] px-2 py-0.5 rounded-md font-semibold ${agent.statusColor}`}>
                    {agent.status}
                  </span>
                </div>

                {/* Status description */}
                <div className="text-xs text-slate-600">
                  {agent.isWorking ? (
                    <div className="flex items-center space-x-1.5 text-amber-700">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                      <span>{agent.description}</span>
                    </div>
                  ) : (
                    <p className="line-clamp-2">{agent.description}</p>
                  )}

                  {agent.tags && (
                    <div className="flex items-center space-x-1.5 pt-2">
                      {agent.tags.map((t) => (
                        <span key={t} className="px-2 py-0.5 bg-slate-100 rounded text-[11px] font-mono text-slate-600">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Footer metrics */}
                <div className="pt-2 border-t border-slate-100 flex items-center space-x-4 text-[11px] text-slate-400 font-mono">
                  <span>{agent.tasks}</span>
                  <span>{agent.time}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right Agent Details Drawer (Dynamic based on selected agent) */}
      {selectedAgent && (
        <div className="w-full lg:w-72 bg-white rounded-2xl border border-slate-200/90 p-5 space-y-5 shadow-2xs shrink-0">
          {/* Header */}
          <div className="flex items-start space-x-3 border-b border-slate-100 pb-4">
            <div className={`w-9 h-9 rounded-xl ${selectedAgent.iconBg} flex items-center justify-center shrink-0 shadow-xs`}>
              <Bot className="w-4.5 h-4.5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-900 capitalize">{selectedAgent.name}</h2>
              <p className="text-xs text-slate-400 capitalize">{selectedAgent.role}</p>
            </div>
          </div>

          {/* Current Action / Description */}
          <div className="space-y-1.5">
            <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
              Current Action
            </span>
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs font-medium text-slate-800">
              {selectedAgent.description}
            </div>
          </div>

          {/* Tools / Capabilities Section */}
          <div className="space-y-2">
            <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
              Tools & Capabilities
            </span>
            <div className="space-y-1.5 text-xs text-slate-700 font-mono">
              {(selectedAgent.tools || selectedAgent.capabilities || []).slice(0, 4).map((tool) => (
                <div key={tool} className="flex items-center space-x-2 p-2 rounded-lg bg-slate-50 border border-slate-100/80 truncate">
                  <span className="text-slate-400">&gt;</span>
                  <span className="truncate">{tool}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Big Metrics Cards */}
          <div className="grid grid-cols-2 gap-3 pt-2">
            <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 text-center">
              <div className="text-xl font-extrabold text-slate-900">
                {selectedAgent.tasks.split(' ')[0]}
              </div>
              <div className="text-[10px] text-slate-400 uppercase font-semibold mt-0.5">Tasks</div>
            </div>

            <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 text-center">
              <div className="text-xl font-extrabold text-slate-900">
                {selectedAgent.time}
              </div>
              <div className="text-[10px] text-slate-400 uppercase font-semibold mt-0.5">Uptime</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
