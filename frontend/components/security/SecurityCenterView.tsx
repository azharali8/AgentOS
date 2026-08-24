'use client';

import React from 'react';
import {
  Shield,
  Lock,
  FileCheck2,
  AlertTriangle,
  CheckCircle2,
  Users,
  Key,
} from 'lucide-react';
import { UserRole } from '../../types';

interface SecurityCenterViewProps {
  userRole: UserRole;
}

export const SecurityCenterView: React.FC<SecurityCenterViewProps> = ({ userRole }) => {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">Security Operations & Governance</h2>
          <p className="text-sm text-slate-400">
            Real-time RBAC policy enforcement, sensitive file isolation, and tool sandbox boundaries
          </p>
        </div>
      </div>

      {/* Role State Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/30 flex items-center justify-center">
            <Users className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <h3 className="font-bold text-slate-200 text-sm">Active Session Authorization</h3>
            <p className="text-xs text-slate-400 font-mono">
              Authenticated Role: <span className="text-blue-400 font-bold">{userRole}</span>
            </p>
          </div>
        </div>

        <span
          className={`text-xs px-3 py-1 rounded font-mono font-bold ${
            userRole === 'ADMIN'
              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
              : userRole === 'DEVELOPER'
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
              : 'bg-slate-800 text-slate-300'
          }`}
        >
          {userRole === 'ADMIN' ? 'FULL ROOT PRIVILEGES' : 'POLICY GATED'}
        </span>
      </div>

      {/* Security Policies Matrix */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center space-x-2 text-emerald-400 text-xs font-bold uppercase tracking-wider">
            <Shield className="w-4 h-4" />
            <span>Workspace Isolation</span>
          </div>
          <p className="text-xs text-slate-400">
            Path traversal (<code className="text-slate-300">..</code>), drive escapes, and UNC paths are blocked by <code className="text-slate-300">WorkspaceService</code>.
          </p>
          <div className="p-2.5 bg-slate-950 rounded border border-slate-800 font-mono text-[11px] text-emerald-400">
            STATUS: ENFORCED (100%)
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center space-x-2 text-amber-400 text-xs font-bold uppercase tracking-wider">
            <Lock className="w-4 h-4" />
            <span>Credential Redaction</span>
          </div>
          <p className="text-xs text-slate-400">
            Files matching <code className="text-slate-300">.env*</code>, <code className="text-slate-300">*.key</code>, and <code className="text-slate-300">.aws/</code> are denied and redacted from LLM logs.
          </p>
          <div className="p-2.5 bg-slate-950 rounded border border-slate-800 font-mono text-[11px] text-amber-400">
            STATUS: REDACTED ON INGEST
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center space-x-2 text-blue-400 text-xs font-bold uppercase tracking-wider">
            <FileCheck2 className="w-4 h-4" />
            <span>Cryptographic Binding</span>
          </div>
          <p className="text-xs text-slate-400">
            Code modifications generate SHA-256 hashes verified before applying any patch.
          </p>
          <div className="p-2.5 bg-slate-950 rounded border border-slate-800 font-mono text-[11px] text-blue-400">
            STATUS: ACTIVE (SHA-256)
          </div>
        </div>
      </div>
    </div>
  );
};