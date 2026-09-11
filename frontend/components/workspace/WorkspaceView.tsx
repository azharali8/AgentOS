'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Folder,
  File,
  Search,
  ChevronRight,
  ChevronDown,
  FileCode2,
  GitBranch,
  Plus,
  RefreshCw,
  FolderGit2,
  Layers,
  Settings2,
  X,
  AlertCircle,
  CheckCircle2,
  Loader2,
  FolderPlus,
  Sparkles,
} from 'lucide-react';
import { WorkspaceTreeResponse, WorkspaceItem } from '../../types';
import { AgentOSClient } from '../../lib/api';

interface WorkspaceViewProps {
  client: AgentOSClient;
  onTaskCreated?: (taskId: string) => void;
}

type ModalMode = 'connect' | 'create';

export const WorkspaceView: React.FC<WorkspaceViewProps> = ({ client, onTaskCreated }) => {
  const [tree, setTree] = useState<WorkspaceTreeResponse | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddProjectModal, setShowAddProjectModal] = useState(false);
  const [modalMode, setModalMode] = useState<ModalMode>('connect');
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [modalSuccess, setModalSuccess] = useState<string | null>(null);

  // Connect existing project state
  const [projectPathInput, setProjectPathInput] = useState('');
  const [projectNameInput, setProjectNameInput] = useState('');

  // Create new project state
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectLocation, setNewProjectLocation] = useState('');
  const [newProjectInstruction, setNewProjectInstruction] = useState('');

  const [repoName, setRepoName] = useState<string>('Workspace');
  const [repoBranch, setRepoBranch] = useState<string>('main');

  const resetModal = useCallback(() => {
    setModalError(null);
    setModalSuccess(null);
    setProjectPathInput('');
    setProjectNameInput('');
    setNewProjectName('');
    setNewProjectLocation('');
    setNewProjectInstruction('');
    setModalLoading(false);
  }, []);

  const openModal = useCallback((mode: ModalMode) => {
    resetModal();
    setModalMode(mode);
    setShowAddProjectModal(true);
  }, [resetModal]);

  const closeModal = useCallback(() => {
    setShowAddProjectModal(false);
    resetModal();
  }, [resetModal]);

  const loadTree = async () => {
    setLoading(true);
    try {
      const [data, info] = await Promise.all([
        client.getWorkspaceTree('').catch(() => null),
        client.getWorkspaceInfo().catch(() => null),
      ]);

      setTree(data);
      if (info?.root) {
        setRepoName(info.root);
      } else if (data?.root) {
        setRepoName(data.root);
      }
      if (info?.git_branch) {
        setRepoBranch(info.git_branch);
      }
    } catch (err) {
      console.error('Failed to load workspace tree:', err);
      setTree(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTree();
  }, []);

  const handleSelectFile = async (item: WorkspaceItem) => {
    if (item.is_dir) return;
    setSelectedFile(item.path);
    setFileLoading(true);
    try {
      const res = await client.getWorkspaceFile(item.path);
      setFileContent(res.content);
    } catch (err) {
      setFileContent('// Unable to read file or file is empty.');
    } finally {
      setFileLoading(false);
    }
  };

  const handleConnectProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectPathInput.trim() || modalLoading) return;
    setModalLoading(true);
    setModalError(null);
    try {
      await client.setWorkspaceRoot(projectPathInput.trim(), projectNameInput.trim());
      closeModal();
      setSelectedFile(null);
      setFileContent(null);
      await loadTree();
    } catch (err: any) {
      setModalError(err.message || 'Failed to connect project directory.');
    } finally {
      setModalLoading(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim() || !newProjectLocation.trim() || modalLoading) return;
    setModalLoading(true);
    setModalError(null);
    try {
      const result = await client.createNewProject(
        newProjectName.trim(),
        newProjectLocation.trim(),
        newProjectInstruction.trim(),
        true,
      );
      if (result.task_id && onTaskCreated) {
        onTaskCreated(result.task_id);
      }
      closeModal();
      setSelectedFile(null);
      setFileContent(null);
      await loadTree();
    } catch (err: any) {
      const msg = err.message || 'Failed to create project.';
      setModalError(msg);
    } finally {
      setModalLoading(false);
    }
  };

  // Real statistics derived from workspace tree
  const stats = useMemo(() => {
    if (!tree || !tree.items) {
      return { totalFiles: 0, totalDirs: 0, totalSizeKB: '0.0' };
    }
    const files = tree.items.filter((i) => !i.is_dir);
    const dirs = tree.items.filter((i) => i.is_dir);
    const totalSize = files.reduce((acc, f) => acc + (f.size || 0), 0);
    return {
      totalFiles: files.length,
      totalDirs: dirs.length,
      totalSizeKB: (totalSize / 1024).toFixed(1),
    };
  }, [tree]);

  const filteredItems = useMemo(() => {
    if (!tree?.items) return [];
    if (!searchQuery.trim()) return tree.items;
    return tree.items.filter(
      (i) =>
        i.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        i.path.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [tree, searchQuery]);

  const isWorkspaceEmpty = !tree || !tree.items || tree.items.length === 0;

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-12">
      {/* Modal: Project Onboarding (two-tab) */}
      {showAddProjectModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-lg w-full p-6 space-y-5 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                  <FolderPlus className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">Project Setup</h3>
                  <p className="text-xs text-slate-500">Connect an existing project or create one from scratch</p>
                </div>
              </div>
              <button
                onClick={closeModal}
                className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Tab switcher */}
            <div className="flex rounded-xl bg-slate-100 p-0.5">
              <button
                type="button"
                onClick={() => { setModalMode('connect'); setModalError(null); }}
                className={`flex-1 flex items-center justify-center space-x-1.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  modalMode === 'connect'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <FolderGit2 className="w-3.5 h-3.5" />
                <span>Connect Existing</span>
              </button>
              <button
                type="button"
                onClick={() => { setModalMode('create'); setModalError(null); }}
                className={`flex-1 flex items-center justify-center space-x-1.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  modalMode === 'create'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Create New Project</span>
              </button>
            </div>

            {/* Connect Existing Tab */}
            {modalMode === 'connect' && (
              <form onSubmit={handleConnectProject} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700">Project Name (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. My Next.js App, Auth Service"
                    value={projectNameInput}
                    onChange={(e) => setProjectNameInput(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-sans"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700">
                    Project Directory Path <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. C:\Users\name\projects\my-app or /home/user/project"
                    value={projectPathInput}
                    onChange={(e) => setProjectPathInput(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                  <p className="text-[11px] text-slate-400">
                    Enter the absolute path to your existing project folder on the machine running AgentOS.
                  </p>
                </div>

                {modalError && (
                  <div className="p-3 bg-rose-50 border border-rose-100 rounded-xl flex items-start space-x-2 text-xs text-rose-700">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>{modalError}</span>
                  </div>
                )}

                <div className="flex items-center justify-end space-x-2 pt-2">
                  <button
                    type="button"
                    onClick={closeModal}
                    disabled={modalLoading}
                    className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!projectPathInput.trim() || modalLoading}
                    className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-xs transition-all"
                  >
                    {modalLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    <span>Connect Project</span>
                  </button>
                </div>
              </form>
            )}

            {/* Create New Project Tab */}
            {modalMode === 'create' && (
              <form onSubmit={handleCreateProject} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700">
                    Project Name <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. TaskFlow, url-shortener, ecommerce-api"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                  <p className="text-[11px] text-slate-400">
                    Alphanumeric, dashes, underscores and dots only.
                  </p>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700">
                    Parent Location <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. D:\Projects or /home/user/workspace"
                    value={newProjectLocation}
                    onChange={(e) => setNewProjectLocation(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                  <p className="text-[11px] text-slate-400">
                    Project will be created at <span className="font-mono">&lt;location&gt;\&lt;name&gt;</span>. The directory must not already exist.
                  </p>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700">Project Instruction</label>
                  <textarea
                    rows={3}
                    placeholder="e.g. Create a FastAPI task management API with JWT authentication, PostgreSQL, and pytest test coverage."
                    value={newProjectInstruction}
                    onChange={(e) => setNewProjectInstruction(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-sans resize-none leading-relaxed"
                  />
                  <p className="text-[11px] text-slate-400">
                    AgentOS will pass this instruction directly to the Supervisor to plan and build your project.
                  </p>
                </div>

                {modalError && (
                  <div className="p-3 bg-rose-50 border border-rose-100 rounded-xl flex items-start space-x-2 text-xs text-rose-700">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>{modalError}</span>
                  </div>
                )}

                <div className="flex items-center justify-end space-x-2 pt-2">
                  <button
                    type="button"
                    onClick={closeModal}
                    disabled={modalLoading}
                    className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!newProjectName.trim() || !newProjectLocation.trim() || modalLoading}
                    className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-xs transition-all"
                  >
                    {modalLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>{newProjectInstruction.trim() ? 'Create & Build' : 'Create Project'}</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* When no project or empty directory, show Empty Onboarding State */}
      {isWorkspaceEmpty && !loading ? (
        <div className="max-w-2xl mx-auto py-16 text-center space-y-6 bg-white rounded-3xl border border-slate-200/90 p-10 shadow-2xs">
          <div className="w-16 h-16 rounded-3xl bg-indigo-50 border border-indigo-100 flex items-center justify-center mx-auto text-indigo-600 shadow-xs">
            <FolderGit2 className="w-8 h-8" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-extrabold text-slate-900 tracking-tight">No Project Connected</h2>
            <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
              Connect a real software project or create a new one from scratch. AgentOS will index your files,
              assemble repository intelligence, and enable specialized AI agents to analyze, test, and build your code.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
            <button
              onClick={() => openModal('connect')}
              className="inline-flex items-center space-x-1.5 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold transition-all shadow-xs"
            >
              <FolderGit2 className="w-4 h-4" />
              <span>Connect Existing Project</span>
            </button>
            <button
              onClick={() => openModal('create')}
              className="inline-flex items-center space-x-1.5 px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition-all shadow-xs"
            >
              <Sparkles className="w-4 h-4" />
              <span>Create New Project</span>
            </button>
            <button
              onClick={loadTree}
              className="inline-flex items-center space-x-1.5 px-4 py-2.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      ) : (
        /* Active Workspace View */
        <div className="flex flex-col md:flex-row gap-6 items-start">
          {/* Left File Explorer */}
          <div className="w-full md:w-72 bg-white rounded-2xl border border-slate-200/90 p-3.5 space-y-3 shrink-0 shadow-2xs">
            {/* Search and Refresh */}
            <div className="flex items-center space-x-2">
              <div className="relative flex-1">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search files..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-8 pr-2.5 py-1.5 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500/30 font-sans"
                />
              </div>
              <button
                onClick={loadTree}
                title="Refresh repository files"
                className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition-colors shrink-0"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {/* Directory Tree */}
            <div className="space-y-0.5 font-mono text-xs text-slate-700 select-none overflow-y-auto max-h-[500px] divide-y divide-slate-50">
              {filteredItems.length === 0 ? (
                <div className="p-4 text-center text-slate-400 text-xs font-sans">
                  No matching files found.
                </div>
              ) : (
                filteredItems.map((item) => {
                  const isSelected = selectedFile === item.path;
                  return (
                    <div
                      key={item.path}
                      onClick={() => handleSelectFile(item)}
                      className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg cursor-pointer transition-colors ${
                        isSelected
                          ? 'bg-indigo-50 text-indigo-900 font-semibold'
                          : 'hover:bg-slate-50 text-slate-700'
                      }`}
                    >
                      <div className="flex items-center space-x-2 truncate">
                        {item.is_dir ? (
                          <Folder className="w-3.5 h-3.5 text-amber-500 shrink-0 fill-amber-500/20" />
                        ) : (
                          <FileCode2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        )}
                        <span className="truncate">{item.name}</span>
                      </div>
                      {!item.is_dir && item.size > 0 && (
                        <span className="text-[10px] text-slate-400 font-mono shrink-0 ml-2">
                          {(item.size / 1024).toFixed(0)}K
                        </span>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Main Details */}
          <div className="flex-1 space-y-6 w-full">
            {/* Repo Header */}
            <div className="flex items-start justify-between">
              <div className="flex items-start space-x-4">
                <div className="w-11 h-11 rounded-2xl bg-indigo-600 flex items-center justify-center text-white font-bold text-sm shadow-xs shrink-0">
                  &lt;/&gt;
                </div>
                <div className="space-y-1">
                  <h1 className="text-xl font-bold text-slate-900">{repoName}</h1>
                  <p className="text-xs text-slate-500">
                    Active connected project environment
                  </p>
                  <div className="flex items-center space-x-3 text-xs text-slate-500 pt-0.5">
                    {repoBranch && (
                      <span className="flex items-center space-x-1 font-mono text-indigo-600 font-medium">
                        <GitBranch className="w-3.5 h-3.5 text-slate-400" />
                        <span>{repoBranch}</span>
                      </span>
                    )}
                    <span>·</span>
                    <span>{stats.totalFiles} files indexed</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => openModal('connect')}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-semibold shadow-2xs transition-colors"
                >
                  <Settings2 className="w-3.5 h-3.5 text-slate-400" />
                  <span>Change Project</span>
                </button>
                <button
                  onClick={() => openModal('create')}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-semibold shadow-2xs transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>New Project</span>
                </button>
                <button
                  onClick={loadTree}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-semibold shadow-2xs transition-colors"
                >
                  <RefreshCw className={`w-3.5 h-3.5 text-slate-400 ${loading ? 'animate-spin' : ''}`} />
                  <span>Sync</span>
                </button>
              </div>
            </div>

            {/* Real Statistics Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
              <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-2xs">
                <div className="text-2xl font-extrabold text-blue-600 font-sans">
                  {stats.totalFiles}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">Indexed Files</div>
              </div>

              <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-2xs">
                <div className="text-2xl font-extrabold text-amber-500 font-sans">
                  {stats.totalDirs}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">Directories</div>
              </div>

              <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-2xs">
                <div className="text-2xl font-extrabold text-indigo-600 font-sans">
                  {stats.totalSizeKB} KB
                </div>
                <div className="text-xs text-slate-500 mt-0.5">Total Size</div>
              </div>

              <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-2xs">
                <div className="text-2xl font-extrabold text-emerald-600 font-sans">
                  Active
                </div>
                <div className="text-xs text-slate-500 mt-0.5">Sandbox State</div>
              </div>
            </div>

            {/* File Preview or Selected File Inspector */}
            <div className="space-y-3">
              <h2 className="text-sm font-bold text-slate-900 tracking-tight">
                {selectedFile ? `File Preview: ${selectedFile}` : 'Workspace Inspector'}
              </h2>
              <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs overflow-hidden">
                {selectedFile ? (
                  <div className="p-4 font-mono text-xs text-slate-800 leading-relaxed overflow-x-auto max-h-[400px]">
                    {fileLoading ? (
                      <div className="text-slate-400 py-6 text-center font-sans">Loading file...</div>
                    ) : (
                      <pre className="whitespace-pre-wrap">{fileContent}</pre>
                    )}
                  </div>
                ) : (
                  <div className="p-8 text-center text-slate-400 text-xs font-sans space-y-1">
                    <FileCode2 className="w-6 h-6 mx-auto text-slate-300 mb-2" />
                    <p>Select any file from the explorer on the left to inspect its contents.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};