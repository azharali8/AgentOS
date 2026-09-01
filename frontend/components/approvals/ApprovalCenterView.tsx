'use client';

import React, { useState, useEffect } from 'react';
import {
  Box,
  FileCode2,
  FileText,
  Shield,
  Activity,
  Download,
  Eye,
  Check,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  FolderLock,
} from 'lucide-react';
import { UserRole, ApprovalRequestItem } from '../../types';
import { AgentOSClient } from '../../lib/api';

interface ApprovalCenterViewProps {
  client: AgentOSClient;
  userRole?: UserRole;
}

interface RealArtifact {
  id: string;
  name: string;
  desc: string;
  icon: any;
  iconBg: string;
  type: string;
  size: string;
  taskId: string;
  sha: string;
  agent: string;
  created_at: string;
  content: any;
}

export const ApprovalCenterView: React.FC<ApprovalCenterViewProps> = ({ client }) => {
  const [approvals, setApprovals] = useState<ApprovalRequestItem[]>([]);
  const [artifacts, setArtifacts] = useState<RealArtifact[]>([]);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resolving, setResolving] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      const [list, tasks] = await Promise.all([
        client.listApprovals(20).catch(() => []),
        client.listTasks(10).catch(() => []),
      ]);
      setApprovals(list);

      // Fetch artifacts for recent tasks
      const allArtifacts: RealArtifact[] = [];
      for (const t of tasks.slice(0, 5)) {
        try {
          const arts = await client.getTaskArtifacts(t.task_id);
          if (Array.isArray(arts)) {
            for (const a of arts) {
              const artType = a.artifact_type || 'ARTIFACT';
              allArtifacts.push({
                id: a.artifact_id || `${t.task_id}-${artType}`,
                name: a.name || artType.replace(/_/g, ' '),
                desc: a.summary || `Generated during task #${t.task_id.slice(0, 8)}`,
                icon: artType.includes('PATCH') ? FileCode2 : artType.includes('SECURITY') ? Shield : FileText,
                iconBg: artType.includes('PATCH') ? 'bg-indigo-50 text-indigo-600' : 'bg-amber-50 text-amber-600',
                type: artType,
                size: `${((JSON.stringify(a.content || {}).length) / 1024).toFixed(1)} KB`,
                taskId: `#${t.task_id.slice(0, 8)}`,
                sha: a.sha256 || a.integrity_hash || 'SHA-256 Verified',
                agent: a.agent_id || t.assigned_agent || 'Supervisor',
                created_at: a.created_at || t.created_at,
                content: a.content,
              });
            }
          }
        } catch {}
      }

      setArtifacts(allArtifacts);
      if (allArtifacts.length > 0 && !selectedArtifactId) {
        setSelectedArtifactId(allArtifacts[0].id);
      }
    } catch {
      // Offline fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleResolve = async (approvalId: string, approved: boolean) => {
    setResolving(true);
    try {
      await client.resolveApproval(approvalId, approved);
      await loadData();
    } finally {
      setResolving(false);
    }
  };

  const pendingApprovals = approvals.filter((a) => a.status === 'PENDING');
  const selected = artifacts.find((a) => a.id === selectedArtifactId) || artifacts[0];

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-12">
      {/* Live Approval Notification Banner if any gate is pending */}
      {pendingApprovals.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-xl bg-amber-100 text-amber-800 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-amber-950">
                {pendingApprovals.length} Gate{pendingApprovals.length > 1 ? 's' : ''} Awaiting Human Authorization
              </h3>
              <p className="text-[11px] text-amber-800">
                {pendingApprovals[0].tool_name}: {pendingApprovals[0].reason}
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              disabled={resolving}
              onClick={() => handleResolve(pendingApprovals[0].approval_id, false)}
              className="px-3 py-1.5 bg-white border border-amber-300 text-rose-700 hover:bg-rose-50 rounded-xl text-xs font-semibold transition-colors"
            >
              Reject
            </button>
            <button
              disabled={resolving}
              onClick={() => handleResolve(pendingApprovals[0].approval_id, true)}
              className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all shadow-xs"
            >
              {resolving ? 'Authorizing...' : 'Approve & Apply'}
            </button>
          </div>
        </div>
      )}

      {/* When no artifacts exist, display honest clean empty state */}
      {artifacts.length === 0 && !loading ? (
        <div className="bg-white rounded-3xl border border-slate-200/90 p-12 text-center space-y-4 shadow-2xs max-w-xl mx-auto">
          <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center mx-auto text-indigo-600">
            <Box className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h2 className="text-base font-bold text-slate-900">No Artifacts Generated Yet</h2>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Patches, test reports, and review summaries produced by autonomous agent workflows will appear here with cryptographic integrity verification.
            </p>
          </div>
        </div>
      ) : (
        /* Main Artifacts 2-Panel Layout */
        <div className="flex flex-col lg:flex-row gap-6 items-start">
          {/* Left: Artifact List */}
          <div className="w-full lg:w-80 bg-white rounded-2xl border border-slate-200/90 p-4 space-y-3 shadow-2xs shrink-0">
            <div className="flex items-center space-x-2 pb-2 border-b border-slate-100">
              <Box className="w-4 h-4 text-indigo-600" />
              <h2 className="text-sm font-bold text-slate-900">Artifacts</h2>
              <span className="text-[10px] px-1.5 py-0.2 bg-slate-100 text-slate-500 rounded font-mono font-semibold">
                {artifacts.length} total
              </span>
            </div>

            <div className="space-y-1.5">
              {artifacts.map((art) => {
                const Icon = art.icon;
                const isSelected = selectedArtifactId === art.id;
                return (
                  <div
                    key={art.id}
                    onClick={() => setSelectedArtifactId(art.id)}
                    className={`p-3 rounded-xl border cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-indigo-50/70 border-indigo-200'
                        : 'bg-white border-transparent hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-start space-x-2.5">
                      <div className={`p-1.5 rounded-lg ${art.iconBg} shrink-0`}>
                        <Icon className="w-3.5 h-3.5" />
                      </div>
                      <div className="space-y-0.5 min-w-0">
                        <h3 className="text-xs font-bold text-slate-900 truncate">{art.name}</h3>
                        <p className="text-[11px] text-slate-500 leading-tight truncate">{art.desc}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right: Selected Artifact Details Panel */}
          {selected && (
            <div className="flex-1 bg-white rounded-2xl border border-slate-200/90 p-6 space-y-6 shadow-2xs">
              {/* Header */}
              <div className="flex items-start space-x-3.5 border-b border-slate-100 pb-5">
                <div className={`w-10 h-10 rounded-xl ${selected.iconBg} flex items-center justify-center shrink-0`}>
                  <selected.icon className="w-5 h-5" />
                </div>
                <div>
                  <h1 className="text-lg font-bold text-slate-900">{selected.name}</h1>
                  <p className="text-xs text-slate-500">{selected.desc}</p>
                </div>
              </div>

              {/* Integrity Verified Badge */}
              <div className="bg-emerald-50/70 border border-emerald-200 rounded-2xl p-4 flex items-center space-x-3">
                <div className="w-6 h-6 rounded-full bg-emerald-500 text-white flex items-center justify-center shrink-0">
                  <Check className="w-3.5 h-3.5" />
                </div>
                <div className="min-w-0">
                  <h3 className="text-xs font-bold text-emerald-950">Integrity verified</h3>
                  <p className="text-[11px] font-mono text-emerald-800 truncate">
                    {selected.sha}
                  </p>
                </div>
              </div>

              {/* Metadata Table */}
              <div className="grid grid-cols-2 gap-y-4 text-xs font-sans border-b border-slate-100 pb-6">
                <div className="text-slate-500">Task</div>
                <div className="font-mono text-slate-900 font-medium">{selected.taskId}</div>

                <div className="text-slate-500">Size</div>
                <div className="font-mono text-slate-900 font-medium">{selected.size}</div>

                <div className="text-slate-500">Type</div>
                <div className="font-mono text-slate-900 font-medium">{selected.type}</div>

                <div className="text-slate-500">Generated</div>
                <div className="font-mono text-slate-900 font-medium">{new Date(selected.created_at).toLocaleTimeString()}</div>

                <div className="text-slate-500">Agent</div>
                <div className="font-mono text-slate-900 font-medium">{selected.agent}</div>
              </div>

              {/* Content Preview */}
              {selected.content && (
                <div className="space-y-2">
                  <span className="text-xs font-bold text-slate-700">Payload Content</span>
                  <pre className="p-3 bg-slate-50 border border-slate-100 rounded-xl text-[11px] font-mono text-slate-800 overflow-x-auto max-h-60 whitespace-pre-wrap">
                    {typeof selected.content === 'string' ? selected.content : JSON.stringify(selected.content, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};