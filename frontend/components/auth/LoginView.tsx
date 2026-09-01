'use client';

import React, { useState } from 'react';
import { Lock, Mail, Shield, ArrowRight, AlertCircle, Sparkles } from 'lucide-react';
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
    <div className="min-h-screen bg-[#f8fafc] bg-grid-pattern flex flex-col justify-center items-center px-4 py-12 select-none text-slate-900 font-sans relative">
      {/* Main Login Card */}
      <div className="w-full max-w-md bg-white border border-slate-200/90 rounded-3xl p-8 shadow-[0_10px_40px_rgba(0,0,0,0.06)] relative z-10 space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-600 to-purple-600 mx-auto flex items-center justify-center text-white shadow-sm shadow-indigo-500/30">
            <Sparkles className="w-5 h-5" />
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
            AgentOS
          </h1>
          <p className="text-xs text-slate-500">
            AI Software Engineering Operating System
          </p>
        </div>

        {error && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl flex items-center space-x-2.5 text-rose-700 text-xs">
            <AlertCircle className="w-4 h-4 text-rose-500 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block text-[11px] font-semibold text-slate-700 mb-1.5">
              Email Address
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="developer@agentos.local"
                className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3 py-2.5 text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-slate-700 mb-1.5">
              Password
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3 py-2.5 text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 transition-all"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl font-semibold text-xs flex items-center justify-center space-x-2 transition-all shadow-sm shadow-indigo-600/20"
          >
            <span>{loading ? 'Authenticating...' : 'Sign In to Workspace'}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </form>

        {/* Quick Profiles */}
        <div className="pt-4 border-t border-slate-100 space-y-2 text-xs">
          <span className="text-[11px] text-slate-400 font-medium block text-center">
            Quick-access Workstation Profiles
          </span>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setPresetUser('user')}
              className={`p-2.5 rounded-xl border text-left transition-all ${
                email === 'azhar@agentos.local'
                  ? 'bg-indigo-50/70 border-indigo-300 text-indigo-900'
                  : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              <span className="block font-bold text-[11px]">Azhar Ali</span>
              <span className="text-[10px] text-slate-400 block truncate">Developer</span>
            </button>

            <button
              type="button"
              onClick={() => setPresetUser('admin')}
              className={`p-2.5 rounded-xl border text-left transition-all ${
                email === 'admin@agentos.local'
                  ? 'bg-indigo-50/70 border-indigo-300 text-indigo-900'
                  : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              <span className="block font-bold text-[11px]">Admin</span>
              <span className="text-[10px] text-slate-400 block truncate">Security Root</span>
            </button>
          </div>
        </div>
      </div>

      <footer className="mt-8 text-center text-slate-400 text-xs space-y-1">
        <p>Security Boundaries: Workspace Sandbox · SHA-256 Checksums · Rate Limiting</p>
      </footer>
    </div>
  );
};