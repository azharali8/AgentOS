'use client';

import React, { useState, useEffect } from 'react';
import {
  Shield,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileCheck2,
  RefreshCw,
  Clock,
  Code2,
} from 'lucide-react';
import { ApprovalRequestItem, UserRole } from '../../types';
import { AgentOSClient } from '../../lib/api';

interface ApprovalCenterViewProps {
  client: AgentOSClient;
  userRole: UserRole;
}

export const ApprovalCenterView: React.FC<ApprovalCenterViewProps> = ({ client, userRole }) => {
  const [approvals, setApprovals] = useState<ApprovalRequestItem[]>([]);
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRequestItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  const loadApprovals = async () => {
    setLoading(true);
    setActionError(null);
    try {
      const list = await client.listApprovals(50);
      setApprovals(list);
      if (list.length > 0 && !selectedApproval) {
        setSelectedApproval(list[0]);
      }
    } catch (err: any) {
      setActionError(err.message || 'Failed to load approvals');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadApprovals();
  }, []);

  const handleResolve = async (approved: boolean) => {
    if (!selectedApproval) return;
    setResolving(true);
    setActionError(null);
    try {
      await client.resolveApproval(
        selectedApproval.approval_id,
        approved,
        approved ? undefined : rejectReason || 'Rejected by developer'
      );
      await loadApprovals();
      setSelectedApproval(null);
      setRejectReason('');
    } catch (err: any) {
      setActionError(err.message || 'Resolution failed');
    } finally {
      setResolving(false);
    }
  };

  const pendingApprovals = approvals.filter((a) => a.status === 'PENDING');
  const resolvedApprovals = approvals.filter((a) => a.status !== 'PENDING');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">Human-in-the-Loop Approval Center</h2>
          <p className="text-sm text-slate-400">
            Authoritative gates for inspecting, approving, and rejecting mutating code patches & operations
          </p>
        </div>
        <button
          onClick={loadApprovals}
          className="flex items-center space-x-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-mono transition-colors border border-slate-700"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh Gates</span>
        </button>
      </div>

      {actionError && (
        <div className="p-3.5 bg-rose-950/40 border border-rose-800/40 rounded-xl flex items-center space-x-2 text-rose-300 text-xs font-mono">
          <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
          <span>Error: {actionError}</span>
        </div>
      )}

      {/* Main Approval Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Approvals List */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col h-[560px]">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Pending Gates ({pendingApprovals.length})
            </span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-2 font-mono text-xs">
            {loading ? (
              <p className="text-slate-500 py-12 text-center">Loading approval gates...</p>
            ) : approvals.length === 0 ? (
              <p className="text-slate-500 py-12 text-center">No approval requests on record.</p>
            ) : (
              approvals.map((appr) => (
                <div
                  key={appr.approval_id}
                  onClick={() => setSelectedApproval(appr)}
                  className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedApproval?.approval_id === appr.approval_id
                      ? 'bg-blue-950/40 border-blue-500/50'
                      : 'bg-slate-950/60 border-slate-800 hover:bg-slate-800/50'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-slate-200">
                      {appr.tool_name}.{appr.operation}
                    </span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                        appr.status === 'PENDING'
                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse'
                          : appr.status === 'APPROVED'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                      }`}
                    >
                      {appr.status}
                    </span>
                  </div>
                  <p className="text-slate-400 text-[11px] truncate mb-1">{appr.reason}</p>
                  <div className="flex items-center justify-between text-[10px] text-slate-500">
                    <span>Task: {appr.task_id.slice(0, 8)}...</span>
                    <span>Risk: {appr.risk_level}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Selected Approval Details & Action Panel */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col h-[560px]">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
            <h3 className="font-semibold text-slate-200 flex items-center text-xs uppercase tracking-wider">
              <Shield className="w-4 h-4 mr-2 text-amber-400" />
              Security Gate Review
            </h3>
            {selectedApproval && (
              <span className="text-[10px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                Risk: {selectedApproval.risk_level}
              </span>
            )}
          </div>

          <div className="flex-1 bg-slate-950 border border-slate-800/80 rounded-lg p-4 font-mono text-xs overflow-y-auto space-y-4">
            {selectedApproval ? (
              <>
                <div className="grid grid-cols-2 gap-3 pb-3 border-b border-slate-800">
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-bold block">Approval ID</span>
                    <p className="text-slate-300">{selectedApproval.approval_id}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-bold block">Task ID</span>
                    <p className="text-slate-300">{selectedApproval.task_id}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-bold block">Tool Operation</span>
                    <p className="text-emerald-400">
                      {selectedApproval.tool_name}:{selectedApproval.operation}
                    </p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-bold block">Cryptographic Hash</span>
                    <p className="text-slate-400 truncate">{selectedApproval.arguments_hash}</p>
                  </div>
                </div>

                <div>
                  <span className="text-[10px] text-slate-500 uppercase font-bold block mb-1">
                    Justification / Reason
                  </span>
                  <p className="text-slate-200 bg-slate-900 border border-slate-800 p-2.5 rounded text-xs">
                    {selectedApproval.reason}
                  </p>
                </div>

                <div>
                  <span className="text-[10px] text-slate-500 uppercase font-bold block mb-1">
                    Proposed Arguments & Patch Payload
                  </span>
                  <pre className="bg-slate-900 border border-slate-800 p-2.5 rounded text-[11px] text-slate-300 overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(selectedApproval.arguments_summary, null, 2)}
                  </pre>
                </div>

                {selectedApproval.status === 'PENDING' && (
                  <div className="pt-3 border-t border-slate-800 space-y-3">
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1">
                        Rejection Reason (Optional)
                      </label>
                      <input
                        type="text"
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                        placeholder="State reason if rejecting..."
                        className="w-full bg-slate-900 border border-slate-800 rounded p-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>

                    <div className="flex items-center justify-end space-x-3">
                      <button
                        disabled={resolving}
                        onClick={() => handleResolve(false)}
                        className="px-4 py-2 bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 rounded text-xs font-mono font-bold transition-colors"
                      >
                        Reject Operation
                      </button>
                      <button
                        disabled={resolving}
                        onClick={() => handleResolve(true)}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-mono font-bold transition-colors shadow-sm"
                      >
                        {resolving ? 'Authorizing...' : 'Authorize & Resume'}
                      </button>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-slate-600 text-center py-24">
                <FileCheck2 className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p>Select an approval request to inspect patch and authorize execution.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};