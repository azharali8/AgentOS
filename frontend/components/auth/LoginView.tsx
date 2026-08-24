'use client';

import React, { useState } from 'react';
import { Lock, Mail, Shield, ArrowRight, AlertCircle, Terminal, Cpu } from 'lucide-react';
import { AgentOSClient } from '../../lib/api';
import { UserProfile } from '../../types';

interface LoginViewProps {
  onLoginSuccess: (token: string, user: UserProfile) => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
  const [email, setEmail] = useState('azhar@agentos.local');
  const [password, setPassword] = useState('agentos123');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const client = new AgentOSClient();
      const res = await client.login(email, password);
      onLoginSuccess(res.token, {
        user_id: res.user_id,
        username: res.username,
        email: res.email,
        role: res.role,
        is_authenticated: true,
      });
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  const setPresetUser = (type: 'user' | 'admin') => {
    if (type === 'admin') {
      setEmail('admin@agentos.local');
      setPassword('admin123');
    } else {
      setEmail('azhar@agentos.local');
      setPassword('agentos123');
    }
    setError(null);
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center px-4 py-12 select-none text-slate-100 font-sans">
      {/* Background Ambience */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(30,58,138,0.15),transparent_70%)] pointer-events-none" />

      {/* Main Console Box */}
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl relative z-10 space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center space-x-2 px-3 py-1 bg-slate-800/80 border border-slate-700/60 rounded-full text-slate-300 font-mono text-[11px]">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>CONTROL PLANE v0.3.0</span>
          </div>
          <h1 className="text-2xl font-bold tracking-widest text-slate-100 font-mono uppercase mt-2">
            AGENTOS
          </h1>
          <p className="text-xs text-slate-400 font-mono">
            AI Engineering Operating System · Secure Workspace
          </p>
        </div>

        {error && (
          <div className="p-3 bg-rose-950/50 border border-rose-800/50 rounded-lg flex items-center space-x-2.5 text-rose-300 text-xs font-mono">
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-4 font-mono text-xs">
          <div>
            <label className="block text-[11px] uppercase font-bold text-slate-400 mb-1.5">
              Engineering Identity (Email)
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="developer@agentos.local"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] uppercase font-bold text-slate-400 mb-1.5">
              Password
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg font-bold font-mono text-xs flex items-center justify-center space-x-2 transition-colors shadow-sm"
          >
            <span>{loading ? 'Authenticating...' : 'Sign In to Workspace'}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </form>

        {/* Workspace Quick-Access Profiles for Testing */}
        <div className="pt-4 border-t border-slate-800/80 space-y-2 font-mono text-[11px]">
          <span className="text-[10px] text-slate-500 uppercase font-bold block text-center">
            Standard Workstation Credentials
          </span>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setPresetUser('user')}
              className={`p-2 rounded border text-left transition-colors ${
                email === 'azhar@agentos.local'
                  ? 'bg-blue-950/40 border-blue-500/60 text-blue-300'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:bg-slate-800/50'
              }`}
            >
              <span className="block font-bold text-[10px]">Azhar Ali (USER)</span>
              <span className="text-[9px] text-slate-500 block truncate">Standard Engineer</span>
            </button>

            <button
              type="button"
              onClick={() => setPresetUser('admin')}
              className={`p-2 rounded border text-left transition-colors ${
                email === 'admin@agentos.local'
                  ? 'bg-rose-950/40 border-rose-500/60 text-rose-300'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:bg-slate-800/50'
              }`}
            >
              <span className="block font-bold text-[10px]">Admin (ADMIN)</span>
              <span className="text-[9px] text-slate-500 block truncate">Root & Security Ops</span>
            </button>
          </div>
        </div>
      </div>

      <footer className="mt-8 text-center text-slate-600 font-mono text-[11px] space-y-1">
        <p>Security Boundaries: Workspace Sandbox · SHA-256 Checksums · Rate Limiting</p>
      </footer>
    </div>
  );
};