'use client';

import React, { useState } from 'react';
import {
  LayoutGrid,
  Bot,
  Shield,
  Key,
  User,
  Check,
} from 'lucide-react';
import { AgentOSClient } from '../../lib/api';

interface SystemHealthViewProps {
  client?: AgentOSClient;
}

export const SystemHealthView: React.FC<SystemHealthViewProps> = () => {
  const [activeCategory, setActiveCategory] = useState('Workspace');

  // Toggle States from Page 8/9
  const [requireApproval, setRequireApproval] = useState(true);
  const [autoApproveLowRisk, setAutoApproveLowRisk] = useState(false);
  const [streamingResponses, setStreamingResponses] = useState(true);
  const [persistContext, setPersistContext] = useState(true);
  const [parallelAgents, setParallelAgents] = useState(true);

  // Dropdowns from Page 9
  const [defaultModel, setDefaultModel] = useState('claude-sonnet-5');
  const [maxParallelAgents, setMaxParallelAgents] = useState('6');
  const [saved, setSaved] = useState(false);

  const categories = [
    { id: 'Workspace', label: 'Workspace', icon: LayoutGrid },
    { id: 'Agents', label: 'Agents', icon: Bot },
    { id: 'Security', label: 'Security', icon: Shield },
    { id: 'API Keys', label: 'API Keys', icon: Key },
    { id: 'Profile', label: 'Profile', icon: User },
  ];

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="max-w-5xl mx-auto flex flex-col md:flex-row gap-8 pb-16 items-start">
      {/* Left Settings Categories (Page 8/9) */}
      <div className="w-full md:w-52 space-y-2 shrink-0">
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block px-3">
          Settings
        </span>
        <div className="space-y-1">
          {categories.map((cat) => {
            const Icon = cat.icon;
            const isActive = activeCategory === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`w-full flex items-center space-x-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-indigo-50/80 text-indigo-600 font-semibold'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <Icon className="w-3.5 h-3.5 text-slate-400" />
                <span>{cat.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Right Settings Form (Page 8/9) */}
      <div className="flex-1 bg-white rounded-2xl border border-slate-200/90 p-6 shadow-2xs space-y-6">
        {/* Title */}
        <div className="space-y-1 border-b border-slate-100 pb-4">
          <h1 className="text-xl font-bold text-slate-900">Workspace</h1>
          <p className="text-xs text-slate-500">
            Configure your AgentOS engineering environment
          </p>
        </div>

        {/* Toggles List */}
        <div className="space-y-5 divide-y divide-slate-100">
          {/* Require Human Approval */}
          <div className="flex items-center justify-between pt-1">
            <div className="space-y-0.5 pr-4">
              <h3 className="text-xs font-bold text-slate-900">Require Human Approval</h3>
              <p className="text-[11px] text-slate-500">
                All file modifications require explicit approval before commit
              </p>
            </div>
            <button
              onClick={() => setRequireApproval(!requireApproval)}
              className={`w-11 h-6 rounded-full transition-colors relative shrink-0 p-0.5 ${
                requireApproval ? 'bg-indigo-600' : 'bg-slate-200'
              }`}
            >
              <div
                className={`w-5 h-5 rounded-full bg-white transition-transform ${
                  requireApproval ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {/* Auto-approve Low Risk Changes */}
          <div className="flex items-center justify-between pt-4">
            <div className="space-y-0.5 pr-4">
              <h3 className="text-xs font-bold text-slate-900">Auto-approve Low Risk Changes</h3>
              <p className="text-[11px] text-slate-500">
                Automatically approve changes marked as low risk by the Review Agent
              </p>
            </div>
            <button
              onClick={() => setAutoApproveLowRisk(!autoApproveLowRisk)}
              className={`w-11 h-6 rounded-full transition-colors relative shrink-0 p-0.5 ${
                autoApproveLowRisk ? 'bg-indigo-600' : 'bg-slate-200'
              }`}
            >
              <div
                className={`w-5 h-5 rounded-full bg-white transition-transform ${
                  autoApproveLowRisk ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {/* Streaming Responses */}
          <div className="flex items-center justify-between pt-4">
            <div className="space-y-0.5 pr-4">
              <h3 className="text-xs font-bold text-slate-900">Streaming Responses</h3>
              <p className="text-[11px] text-slate-500">
                Show agent responses as they are generated
              </p>
            </div>
            <button
              onClick={() => setStreamingResponses(!streamingResponses)}
              className={`w-11 h-6 rounded-full transition-colors relative shrink-0 p-0.5 ${
                streamingResponses ? 'bg-indigo-600' : 'bg-slate-200'
              }`}
            >
              <div
                className={`w-5 h-5 rounded-full bg-white transition-transform ${
                  streamingResponses ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {/* Persist Context Between Tasks */}
          <div className="flex items-center justify-between pt-4">
            <div className="space-y-0.5 pr-4">
              <h3 className="text-xs font-bold text-slate-900">Persist Context Between Tasks</h3>
              <p className="text-[11px] text-slate-500">
                Keep file and symbol context across task sessions
              </p>
            </div>
            <button
              onClick={() => setPersistContext(!persistContext)}
              className={`w-11 h-6 rounded-full transition-colors relative shrink-0 p-0.5 ${
                persistContext ? 'bg-indigo-600' : 'bg-slate-200'
              }`}
            >
              <div
                className={`w-5 h-5 rounded-full bg-white transition-transform ${
                  persistContext ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {/* Parallel Agent Execution */}
          <div className="flex items-center justify-between pt-4">
            <div className="space-y-0.5 pr-4">
              <h3 className="text-xs font-bold text-slate-900">Parallel Agent Execution</h3>
              <p className="text-[11px] text-slate-500">
                Allow multiple agents to work simultaneously when possible
              </p>
            </div>
            <button
              onClick={() => setParallelAgents(!parallelAgents)}
              className={`w-11 h-6 rounded-full transition-colors relative shrink-0 p-0.5 ${
                parallelAgents ? 'bg-indigo-600' : 'bg-slate-200'
              }`}
            >
              <div
                className={`w-5 h-5 rounded-full bg-white transition-transform ${
                  parallelAgents ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Dropdowns Section (Page 9) */}
        <div className="space-y-4 pt-2 border-t border-slate-100">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-900">Default Model</span>
            <select
              value={defaultModel}
              onChange={(e) => setDefaultModel(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500/30 w-44"
            >
              <option value="claude-sonnet-5">claude-sonnet-5</option>
              <option value="claude-3-5-sonnet">claude-3-5-sonnet</option>
              <option value="gpt-4o">gpt-4o</option>
              <option value="deepseek-v3">deepseek-v3</option>
            </select>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-900">Max Parallel Agents</span>
            <select
              value={maxParallelAgents}
              onChange={(e) => setMaxParallelAgents(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500/30 w-44"
            >
              <option value="2">2</option>
              <option value="4">4</option>
              <option value="6">6</option>
              <option value="8">8</option>
            </select>
          </div>
        </div>

        {/* Save Settings Button (Page 9) */}
        <div className="flex justify-end pt-4 border-t border-slate-100">
          <button
            onClick={handleSave}
            className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold transition-all shadow-xs"
          >
            {saved ? <Check className="w-3.5 h-3.5" /> : null}
            <span>{saved ? 'Saved!' : 'Save Settings'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};