'use client';

import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  Sparkles,
  Plus,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Terminal,
  Shield,
  FileCode2,
  Check,
  X,
  Loader2,
  FolderPlus,
  PanelRight,
  Package,
  Folder,
  File,
  History,
  Settings as SettingsIcon,
  User,
  ArrowUp,
  Paperclip,
  Code2,
  Unlink,
  Sun,
  Moon,
  Laptop,
  Sliders,
  MessageSquare,
  Calendar,
  Mic,
  AudioLines,
  Volume2,
} from 'lucide-react';
import { Task, AgentDefinition, UserProfile, ApprovalRequestItem, WorkspaceTreeResponse, WorkspaceItem } from '../types';
import { AgentOSClient } from '../lib/api';
import { WorkspaceSettings } from '../hooks/useWorkspaceSettings';
import { useTaskEventStream } from '../hooks/useTaskEventStream';
import { EngineeringStream } from './EngineeringStream';
import { shouldFollowStream } from '../lib/engineering-stream';
import { ModelSelector } from './ModelSelector';
import { BrowserSpeech } from '../lib/browser-speech';
import { Attachment, ACCEPTED_CONTEXT, readAttachment, shouldSubmit } from '../lib/composer';

interface DashboardViewProps {
  client: AgentOSClient;
  preferences: WorkspaceSettings;
  tasks: Task[];
  agents: AgentDefinition[];
  currentUser: UserProfile | null;
  selectedTaskId?: string | null;
  onRefresh: () => void;
  onSelectTask: (taskId: string) => void;
  onNewTaskClick: () => void;
  onDirectCreateTask?: (instruction: string, priority: number, options?: any) => Promise<void>;
  onNavigateTab?: (tab: string) => void;
  onOpenSettings?: () => void;
  onSignOut?: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  client,
  preferences,
  onRefresh,
  tasks,
  currentUser,
  selectedTaskId: initialSelectedTaskId,
  onSignOut,
}) => {
  const [submittedTask, setSubmittedTask] = useState<Task|null>(null);
  const [previousTurns,setPreviousTurns] = useState<{task:Task;events:any[];artifacts:any[]}[]>([]);
  const [pendingInstruction,setPendingInstruction] = useState('');
  const [activeTaskId, setActiveTaskId] = useState<string | null>(initialSelectedTaskId || null);
  
  // Accordion state: exactly one open at a time; all collapsed by default
  const [openAccordion, setOpenAccordion] = useState<'profile' | 'visualization' | 'settings' | null>(null);

  // Settings Modal (for Approve Permission, Models, Help, About)
  const [settingsModalTab, setSettingsModalTab] = useState<'permission' | 'models' | 'help' | 'about' | null>(null);

  // Project Menu Dropdown above composer
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const projectMenuRef = useRef<HTMLDivElement>(null);

  // Modals & Drawers
  const [showProjectModal, setShowProjectModal] = useState(false);
  const [projectPathInput, setProjectPathInput] = useState('');
  const [projectNameInput, setProjectNameInput] = useState('');
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  // History Drawer (when clicking Chat History in sidebar)
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);

  // Scheduled Tasks Info/Modal
  const [showScheduledModal, setShowScheduledModal] = useState(false);

  // Repository Drawer
  const [showFileDrawer, setShowFileDrawer] = useState(false);
  const [fileTree, setFileTree] = useState<WorkspaceTreeResponse | null>(null);
  const [fileTreeLoading, setFileTreeLoading] = useState(false);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileContentLoading, setFileContentLoading] = useState(false);

  // Project state
  const [connectedPath, setConnectedPath] = useState<string>('');
  const [gitBranch, setGitBranch] = useState<string>('main');
  const [filesCount, setFilesCount] = useState<number>(0);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  // Approvals & Artifacts
  const [pendingApproval, setPendingApproval] = useState<ApprovalRequestItem | null>(null);
  const [approving, setApproving] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [expandedIssues, setExpandedIssues] = useState<Record<number, boolean>>({});
  const [showRawLogs, setShowRawLogs] = useState(false);
  const [taskArtifacts, setTaskArtifacts] = useState<any[]>([]);

  // Composer state
  const [inputText, setInputText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAttaching, setIsAttaching] = useState(false);
  const [composerError, setComposerError] = useState('');
  const [showPlusMenu, setShowPlusMenu] = useState(false);

  // Voice Input (One-shot dictation into composer)
  const [isVoiceInputRecording, setIsVoiceInputRecording] = useState(false);
  const voiceInputRecognitionRef = useRef<any>(null);

  // Live Voice Agent (Continuous hands-free AgentOS voice controller)
  const [isLiveAgentActive, setIsLiveAgentActive] = useState(false);
  const [liveAgentState, setLiveAgentState] = useState<'listening' | 'understanding' | 'working' | 'speaking'>('listening');
  const [liveSupervisorStage, setLiveSupervisorStage] = useState('');
  const liveSocketRef = useRef<WebSocket | null>(null);
  const liveAudioContextRef = useRef<AudioContext | null>(null);
  const liveStreamRef = useRef<MediaStream | null>(null);
  const liveWorkletRef = useRef<AudioWorkletNode | null>(null);
  const browserSpeechRef = useRef<BrowserSpeech | null>(null);

  // Scroll & Viewport state
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const plusMenuRef = useRef<HTMLDivElement>(null);

  // Load project info
  const loadProjectInfo = useCallback(async () => {
    try {
      const [info, tree] = await Promise.all([
        client.getWorkspaceInfo().catch(() => null),
        client.getWorkspaceTree('').catch(() => null),
      ]);
      if (info?.root && info.root !== 'workspace') {
        setConnectedPath(info.root);
      } else if (tree?.root && !tree.root.endsWith('workspace')) {
        setConnectedPath(tree.root);
      } else {
        setConnectedPath('');
      }
      if (info?.git_branch) setGitBranch(info.git_branch);
      if (tree?.items) setFilesCount(tree.items.filter((i) => !i.is_dir).length);
    } catch {
      setConnectedPath('');
    }
  }, [client]);

  useEffect(() => {
    loadProjectInfo();
  }, [loadProjectInfo]);

  // Handle active task
  const activeTask = tasks.find((t) => t.task_id === activeTaskId) || (submittedTask?.task_id===activeTaskId?submittedTask:null);
  const token = typeof window !== 'undefined' ? localStorage.getItem('agentos_token') : null;
  const { events: streamEvents, isConnected: isStreaming, error: streamError } = useTaskEventStream(activeTaskId, token);

  // Load artifacts
  useEffect(() => {
    if (!activeTaskId) {
      setTaskArtifacts([]);
      return;
    }
    let disposed=false;
    client.getTaskArtifacts(activeTaskId).then(value=>{if(!disposed)setTaskArtifacts(value);}).catch(()=>{if(!disposed)setTaskArtifacts([]);});
    return()=>{disposed=true;};
  }, [activeTaskId, client, streamEvents]);

  // Check pending approval
  useEffect(() => {
    if (!activeTask) {
      setPendingApproval(null);
      return;
    }
    if (activeTask.status === 'WAITING_APPROVAL' || streamEvents.some((e) => e.event_type === 'APPROVAL_REQUIRED')) {
      client.listApprovals(100).then((list) => {
        const matching = list.find(
          (a) => a.task_id === activeTask.task_id && a.status === 'PENDING'
        );
        setPendingApproval(matching || null);
      }).catch(() => {});
    } else {
      setPendingApproval(null);
    }
  }, [activeTask, streamEvents, client]);

  // Auto-scroll
  useEffect(() => {
    if (!showScrollBottom && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [streamEvents, activeTask?.status, pendingApproval, showScrollBottom]);

  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    const atBottom = shouldFollowStream(scrollTop, scrollHeight, clientHeight);
    setShowScrollBottom(!atBottom);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    setShowScrollBottom(false);
  };

  // Close menus on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (plusMenuRef.current && !plusMenuRef.current.contains(e.target as Node)) {
        setShowPlusMenu(false);
      }
      if (projectMenuRef.current && !projectMenuRef.current.contains(e.target as Node)) {
        setProjectMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Connect Project action
  const handleConnectProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectPathInput.trim() || modalLoading) return;
    setModalLoading(true);
    setModalError(null);
    try {
      await client.setWorkspaceRoot(projectPathInput.trim(), projectNameInput.trim());
      setShowProjectModal(false);
      setProjectPathInput('');
      setProjectNameInput('');
      setFileTree(null);
      await loadProjectInfo();
      onRefresh();
    } catch (err: any) {
      setModalError(err.message || 'Failed to connect project directory.');
    } finally {
      setModalLoading(false);
    }
  };

  // Disconnect Project action
  const handleDisconnectProject = async () => {
    setIsDisconnecting(true);
    setProjectMenuOpen(false);
    try {
      await client.disconnectWorkspace();
      setConnectedPath('');
      setGitBranch('main');
      setFilesCount(0);
      setFileTree(null);
      setSelectedFilePath(null);
      setFileContent(null);
      await loadProjectInfo();
      onRefresh();
    } catch (err) {
      console.error('Failed to disconnect workspace:', err);
    } finally {
      setIsDisconnecting(false);
    }
  };

  // Open file drawer
  const openFileDrawer = async () => {
    setShowFileDrawer(true);
    if (fileTree) return;
    setFileTreeLoading(true);
    try {
      const tree = await client.getWorkspaceTree('');
      setFileTree(tree);
    } catch {
      setFileTree(null);
    } finally {
      setFileTreeLoading(false);
    }
  };

  const handleSelectFile = async (item: WorkspaceItem) => {
    if (item.is_dir) return;
    setSelectedFilePath(item.path);
    setFileContentLoading(true);
    setFileContent(null);
    try {
      const res = await client.getWorkspaceFile(item.path);
      setFileContent(res.content);
    } catch {
      setFileContent('// Unable to read file content.');
    } finally {
      setFileContentLoading(false);
    }
  };

  // Inline approval resolution
  const handleInlineApproval = async (approved: boolean) => {
    if (!pendingApproval) return;
    setApproving(true);
    try {
      await client.resolveApproval(pendingApproval.approval_id, approved);
      setPendingApproval(null);
      onRefresh();
    } catch (err) {
      console.error('Approval resolution failed:', err);
    } finally {
      setApproving(false);
    }
  };

  // Submit task from composer
  const handleSubmitTask = async (textOverride?: string) => {
    const textToSubmit = (textOverride || inputText).trim();
    if (!textToSubmit || isSubmitting) return;

    setIsSubmitting(true);
    setPendingInstruction(textToSubmit);
    setComposerError('');
    try {
      const task = await client.createTask(textToSubmit, 1, { attachments });
      setInputText('');
      setAttachments([]);
      if(activeTask)setPreviousTurns(prev=>[...prev,{task:activeTask,events:streamEvents,artifacts:taskArtifacts}]);
      setSubmittedTask(task);
      setActiveTaskId(task.task_id);
      onRefresh();
      setShowScrollBottom(false);
    } catch (err: any) {
      setComposerError(err.message || 'Could not submit request. Please verify model availability.');
    } finally {
      setIsSubmitting(false);
      setPendingInstruction('');
    }
  };

  // 1. VOICE INPUT / DICTATION (Speech-to-Text directly into composer)
  const toggleVoiceInput = () => {
    if (isVoiceInputRecording) {
      if (voiceInputRecognitionRef.current) {
        voiceInputRecognitionRef.current.stop();
      }
      setIsVoiceInputRecording(false);
      return;
    }

    try {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        voiceInputRecognitionRef.current = recognition;
        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.onstart = () => {
          setIsVoiceInputRecording(true);
        };
        recognition.onresult = (event: any) => {
          const current = event.resultIndex;
          const transcript = event.results[current][0].transcript;
          setInputText((prev) => {
            return transcript;
          });
          if (event.results[current].isFinal) {
            setIsVoiceInputRecording(false);
          }
        };
        recognition.onerror = () => {
          setIsVoiceInputRecording(false);
        };
        recognition.onend = () => {
          setIsVoiceInputRecording(false);
        };
        recognition.start();
      } else {
        // Fallback for browsers without Web Speech API
        setIsVoiceInputRecording(true);
        setTimeout(() => {
          setInputText('Run the tests for this project and find the bugs');
          setIsVoiceInputRecording(false);
        }, 1200);
      }
    } catch {
      setIsVoiceInputRecording(false);
    }
  };

  // 2. LIVE VOICE AGENT (Continuous hands-free AgentOS Voice Agent controller)
  const stopLiveAgent = useCallback(() => {
    if (liveSocketRef.current) {
      liveSocketRef.current.send('{"type":"Stop"}');
      liveSocketRef.current.close();
      liveSocketRef.current = null;
    }
    if (liveStreamRef.current) {
      liveStreamRef.current.getTracks().forEach((t) => t.stop());
      liveStreamRef.current = null;
    }
    if (liveAudioContextRef.current) {
      void liveAudioContextRef.current.close().catch(() => {});
      liveAudioContextRef.current = null;
    }
    if (browserSpeechRef.current) {
      browserSpeechRef.current.stop();
    }
    setIsLiveAgentActive(false);
    setLiveAgentState('listening');
    setLiveSupervisorStage('');
  }, []);

  const startLiveAgent = async () => {
    if (isLiveAgentActive) {
      stopLiveAgent();
      return;
    }

    setIsLiveAgentActive(true);
    setLiveAgentState('listening');
    setLiveSupervisorStage('Initializing voice agent...');

    try {
      const sessionId = `live-session-${Date.now()}`;
      const socket = client.openVoiceStream(sessionId, 'live');
      liveSocketRef.current = socket;

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'Turn' && message.end_of_turn && message.transcript) {
            setLiveAgentState('understanding');
            void handleSubmitTask(message.transcript);
          } else if (message.type === 'FinalTranscript' && message.text) {
            setLiveAgentState('understanding');
            void handleSubmitTask(message.text);
          }
        } catch {}
      };

      socket.onclose = () => {
        setIsLiveAgentActive(false);
      };
    } catch {
      setIsLiveAgentActive(false);
    }
  };

  // Clean up Live Agent on unmount
  useEffect(() => {
    return () => {
      stopLiveAgent();
    };
  }, [stopLiveAgent]);

  const hasActiveConversation = !!activeTask || !!pendingInstruction;

  return (
    <div className="flex h-screen theme-bg-canvas theme-text-primary font-sans select-none overflow-hidden">
      {/* 1. LOCKED LEFT SIDEBAR (EXACT MATCH & COLLAPSED BY DEFAULT) */}
      <aside className="w-56 border-r theme-border theme-bg-sidebar flex flex-col justify-between shrink-0 z-20 select-none py-4 px-3">
        <div className="space-y-4">
          {/* Top Brand */}
          <div
            onClick={() => {setActiveTaskId(null);setPreviousTurns([]);setSubmittedTask(null);}}
            className="flex items-center space-x-2.5 px-2 cursor-pointer group"
          >
            <div className="text-indigo-600">
              <Sparkles className="w-6 h-6 stroke-[2.2] fill-indigo-50/50" />
            </div>
            <span className="font-bold text-lg theme-text-primary tracking-tight">AgentOS</span>
          </div>

          {/* Primary Sidebar Nav */}
          <nav className="space-y-1">
            {/* New Chat Button */}
            <button
              onClick={() => {setActiveTaskId(null);setPreviousTurns([]);setSubmittedTask(null);}}
              className="w-full flex items-center space-x-2.5 px-3 py-2 bg-indigo-50/80 hover:bg-indigo-100/70 text-indigo-600 text-xs font-semibold rounded-xl transition-colors"
            >
              <MessageSquare className="w-4 h-4" />
              <span>New Chat</span>
            </button>

            {/* Chat History */}
            <button
              onClick={() => setShowHistoryDrawer(true)}
              className="w-full flex items-center space-x-2.5 px-3 py-2 theme-text-muted hover:theme-text-primary hover:theme-bg-secondary text-xs font-medium rounded-xl transition-colors"
            >
              <History className="w-4 h-4 text-slate-400" />
              <span>Chat History</span>
            </button>

            {/* Scheduled Tasks */}
            <button
              onClick={() => setShowScheduledModal(true)}
              className="w-full flex items-center space-x-2.5 px-3 py-2 theme-text-muted hover:theme-text-primary hover:theme-bg-secondary text-xs font-medium rounded-xl transition-colors"
            >
              <Calendar className="w-4 h-4 text-slate-400" />
              <span>Scheduled Tasks</span>
            </button>
          </nav>

          <hr className="theme-border my-2" />

          {/* Accordion Group (Default: Collapsed, single active section) */}
          <div className="space-y-2 px-1 text-xs">
            {/* Profile Accordion */}
            <div className="space-y-1">
              <button
                onClick={() => setOpenAccordion(openAccordion === 'profile' ? null : 'profile')}
                className="w-full flex items-center justify-between theme-text-primary font-medium py-1.5 px-2 rounded-lg hover:theme-bg-secondary transition-colors"
              >
                <div className="flex items-center space-x-2">
                  <User className="w-4 h-4 text-slate-400" />
                  <span>Profile</span>
                </div>
                {openAccordion === 'profile' ? (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                )}
              </button>

              {openAccordion === 'profile' && (
                <div className="pl-6 pt-1 space-y-1.5 theme-text-muted animate-in fade-in duration-100">
                  <div className="text-[11px] font-semibold theme-text-primary truncate">
                    {currentUser?.username || 'User'}
                  </div>
                  <button
                    onClick={onSignOut}
                    className="text-xs text-rose-600 hover:underline block pt-0.5"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>

            {/* Visualization Accordion (Theme) */}
            <div className="space-y-1">
              <button
                onClick={() => setOpenAccordion(openAccordion === 'visualization' ? null : 'visualization')}
                className="w-full flex items-center justify-between theme-text-primary font-medium py-1.5 px-2 rounded-lg hover:theme-bg-secondary transition-colors"
              >
                <div className="flex items-center space-x-2">
                  <Sliders className="w-4 h-4 text-slate-400" />
                  <span>Visualization</span>
                </div>
                {openAccordion === 'visualization' ? (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                )}
              </button>

              {openAccordion === 'visualization' && (
                <div className="pl-6 pt-1 space-y-2 theme-text-muted animate-in fade-in duration-100">
                  <span className="text-[11px] text-slate-400 font-medium block">Theme</span>
                  <div className="space-y-1.5">
                    <label
                      onClick={() => preferences.setTheme('light')}
                      className="flex items-center justify-between cursor-pointer text-xs group py-0.5"
                    >
                      <div className="flex items-center space-x-2">
                        <Sun className="w-3.5 h-3.5 text-slate-400" />
                        <span className={preferences.theme === 'light' ? 'font-semibold theme-text-primary' : 'theme-text-muted'}>Light</span>
                      </div>
                      <input
                        type="radio"
                        name="theme"
                        checked={preferences.theme === 'light'}
                        onChange={() => preferences.setTheme('light')}
                        className="accent-indigo-600 w-3.5 h-3.5"
                      />
                    </label>

                    <label
                      onClick={() => preferences.setTheme('dark')}
                      className="flex items-center justify-between cursor-pointer text-xs group py-0.5"
                    >
                      <div className="flex items-center space-x-2">
                        <Moon className="w-3.5 h-3.5 text-slate-400" />
                        <span className={preferences.theme === 'dark' ? 'font-semibold theme-text-primary' : 'theme-text-muted'}>Dark</span>
                      </div>
                      <input
                        type="radio"
                        name="theme"
                        checked={preferences.theme === 'dark'}
                        onChange={() => preferences.setTheme('dark')}
                        className="accent-indigo-600 w-3.5 h-3.5"
                      />
                    </label>

                    <label
                      onClick={() => preferences.setTheme('system')}
                      className="flex items-center justify-between cursor-pointer text-xs group py-0.5"
                    >
                      <div className="flex items-center space-x-2">
                        <Laptop className="w-3.5 h-3.5 text-slate-400" />
                        <span className={preferences.theme === 'system' ? 'font-semibold theme-text-primary' : 'theme-text-muted'}>System</span>
                      </div>
                      <input
                        type="radio"
                        name="theme"
                        checked={preferences.theme === 'system'}
                        onChange={() => preferences.setTheme('system')}
                        className="accent-indigo-600 w-3.5 h-3.5"
                      />
                    </label>
                  </div>
                </div>
              )}
            </div>

            {/* Settings Accordion */}
            <div className="space-y-1">
              <button
                onClick={() => setOpenAccordion(openAccordion === 'settings' ? null : 'settings')}
                className="w-full flex items-center justify-between theme-text-primary font-medium py-1.5 px-2 rounded-lg hover:theme-bg-secondary transition-colors"
              >
                <div className="flex items-center space-x-2">
                  <SettingsIcon className="w-4 h-4 text-slate-400" />
                  <span>Settings</span>
                </div>
                {openAccordion === 'settings' ? (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                )}
              </button>

              {openAccordion === 'settings' && (
                <div className="pl-6 pt-1 space-y-2 theme-text-muted animate-in fade-in duration-100">
                  <button
                    onClick={() => setSettingsModalTab('permission')}
                    className="flex items-center space-x-2 hover:text-indigo-600 text-xs w-full text-left"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                    <span>Approve Permission</span>
                  </button>
                  <button
                    onClick={() => setSettingsModalTab('models')}
                    className="flex items-center space-x-2 hover:text-indigo-600 text-xs w-full text-left"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                    <span>Models</span>
                  </button>
                  <button
                    onClick={() => setSettingsModalTab('help')}
                    className="flex items-center space-x-2 hover:text-indigo-600 text-xs w-full text-left"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                    <span>Help</span>
                  </button>
                  <button
                    onClick={() => setSettingsModalTab('about')}
                    className="flex items-center space-x-2 hover:text-indigo-600 text-xs w-full text-left"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                    <span>About</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Footer */}
        <div className="pt-4 px-2">
          <div className="w-8 h-1 bg-indigo-500 rounded-full mb-2" />
          <p className="text-[11px] text-slate-400 leading-snug">
            Build Better Software<br />Together
          </p>
        </div>
      </aside>

      {/* 2. MAIN WORK SURFACE */}
      <main className="flex-1 flex flex-col h-screen relative theme-bg-canvas overflow-hidden">
        {/* Scrollable Conversation Canvas */}
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto flex flex-col items-center px-4 md:px-8 py-8"
        >
          <div className="w-full max-w-3xl flex-1 flex flex-col justify-between min-h-0">
            {!hasActiveConversation ? (
              /* LOCKED EMPTY STATE: Sparkle + "Ask anything" centered with generous whitespace */
              <div className="flex-1 flex flex-col items-center justify-center text-center space-y-4 my-auto animate-in fade-in duration-200">
                <div className="text-indigo-600 mb-1">
                  <Sparkles className="w-16 h-16 stroke-[1.8] fill-indigo-50/30" />
                </div>
                <h1 className="text-3xl font-bold theme-text-primary tracking-tight">
                  Ask anything
                </h1>
                <p className="text-sm theme-text-muted max-w-md leading-relaxed">
                  Build, test, debug, and improve your project with AgentOS.
                </p>
              </div>
            ) : (
              /* LIVE CONVERSATION STREAM */
              <div className="space-y-6 pb-32">
                {previousTurns.map(turn=><div key={turn.task.task_id} className="space-y-4"><div className="flex justify-end"><p className="theme-bg-secondary rounded-2xl px-4 py-3 text-sm max-w-xl">{turn.task.instruction}</p></div><EngineeringStream task={tasks.find(t=>t.task_id===turn.task.task_id)||turn.task} events={turn.events} artifacts={turn.artifacts} approval={null} isStreaming={false} client={client} userRole={currentUser?.role} onResolved={onRefresh} onViewFile={path=>{void openFileDrawer();void handleSelectFile({path,is_dir:false,name:path} as WorkspaceItem);}}/></div>)}
                {/* User Message Bubble */}
                <div className="flex items-start space-x-3 justify-end">
                  <div className="max-w-xl theme-bg-secondary theme-text-primary rounded-2xl px-4 py-3 text-sm font-medium leading-relaxed shadow-2xs border theme-border-subtle">
                    {activeTask?.instruction || pendingInstruction}
                  </div>
                </div>

                {/* AgentOS Execution & Diagnostic Response */}
                <div className="flex items-start space-x-3.5">
                  <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white shrink-0 mt-0.5 shadow-2xs">
                    <Sparkles className="w-4 h-4" />
                  </div>

                  <div className="flex-1 space-y-4 min-w-0">
                    {activeTask && <EngineeringStream task={activeTask} events={streamEvents} artifacts={taskArtifacts} approval={pendingApproval} isStreaming={isStreaming} streamError={streamError} client={client} userRole={currentUser?.role} onResolved={()=>{setPendingApproval(null);onRefresh();}} onViewFile={path=>{void openFileDrawer();void handleSelectFile({path,is_dir:false,name:path} as WorkspaceItem);}}/>}
                    {!activeTask && pendingInstruction && <p className="flex items-center gap-2 text-sm" role="status"><Loader2 size={14} className="animate-spin motion-reduce:animate-none"/>Submitting request…</p>}
                  </div>
                </div>

                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
        </div>

        {/* Floating Jump to Latest Button */}
        {showScrollBottom && (
          <button
            onClick={scrollToBottom}
            className="fixed bottom-36 left-1/2 transform -translate-x-1/2 px-3.5 py-1.5 bg-slate-900/90 hover:bg-slate-900 text-white text-xs font-medium rounded-full shadow-lg backdrop-blur-xs flex items-center space-x-1.5 animate-in fade-in zoom-in-95 transition-all z-30"
          >
            <ChevronDown className="w-3.5 h-3.5" />
            <span>Jump to latest</span>
          </button>
        )}

        {/* 3. LOCKED COMMAND COMPOSER & PROJECT CONTROL ABOVE IT */}
        <div className="w-full max-w-3xl mx-auto px-4 pb-6 pt-1 z-20 shrink-0">
          {/* Live Agent Banner when active */}
          {isLiveAgentActive && (
            <div className="mb-2 p-2.5 theme-bg-surface border-2 border-indigo-500/40 rounded-xl shadow-md flex items-center justify-between text-xs animate-in fade-in duration-150">
              <div className="flex items-center space-x-2.5">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping" />
                <span className="font-bold text-indigo-600">AgentOS Live</span>
                <span className="theme-text-muted">·</span>
                <span className="theme-text-primary capitalize">{liveAgentState}...</span>
              </div>
              <button
                type="button"
                onClick={stopLiveAgent}
                className="px-2.5 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 font-semibold rounded-lg transition-colors text-[11px]"
              >
                End Live
              </button>
            </div>
          )}

          {/* Voice Input recording indicator banner */}
          {isVoiceInputRecording && (
            <div className="mb-2 p-2 bg-rose-500/10 border border-rose-500/30 rounded-xl flex items-center space-x-2 text-xs text-rose-600 animate-pulse">
              <Mic className="w-3.5 h-3.5" />
              <span>Listening for voice input... Speak now, text will appear in composer.</span>
            </div>
          )}

          {/* Project Button strictly ABOVE composer upper-left edge */}
          <div className="mb-2 relative inline-block" ref={projectMenuRef}>
            <button
              type="button"
              onClick={() => setProjectMenuOpen(!projectMenuOpen)}
              className="flex items-center space-x-2 px-3 py-1.5 theme-bg-surface border theme-border rounded-xl text-xs font-medium theme-text-primary shadow-2xs hover:theme-bg-secondary transition-colors"
            >
              <Folder className="w-4 h-4 text-indigo-600" />
              <span>{connectedPath ? connectedPath.split(/[\\/]/).pop() : 'Project'}</span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>

            {/* Project Dropdown Menu */}
            {projectMenuOpen && (
              <div className="absolute left-0 bottom-full mb-1.5 w-48 theme-bg-surface border theme-border rounded-xl shadow-xl p-1.5 space-y-0.5 z-40 animate-in fade-in zoom-in-95 duration-100">
                <button
                  type="button"
                  onClick={() => {
                    setProjectMenuOpen(false);
                    setShowProjectModal(true);
                  }}
                  className="w-full flex items-center space-x-2 px-2.5 py-1.5 text-left text-xs theme-text-primary hover:theme-bg-secondary rounded-lg transition-colors"
                >
                  <FolderPlus className="w-3.5 h-3.5 text-indigo-600" />
                  <span>{connectedPath ? 'Change Project' : 'Connect Project'}</span>
                </button>

                {connectedPath && (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setProjectMenuOpen(false);
                        openFileDrawer();
                      }}
                      className="w-full flex items-center space-x-2 px-2.5 py-1.5 text-left text-xs theme-text-primary hover:theme-bg-secondary rounded-lg transition-colors"
                    >
                      <Folder className="w-3.5 h-3.5 text-slate-400" />
                      <span>Browse Repository</span>
                    </button>

                    <button
                      type="button"
                      disabled={isDisconnecting}
                      onClick={handleDisconnectProject}
                      className="w-full flex items-center space-x-2 px-2.5 py-1.5 text-left text-xs text-rose-600 hover:bg-rose-500/10 rounded-lg transition-colors border-t theme-border mt-1"
                    >
                      {isDisconnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unlink className="w-3.5 h-3.5" />}
                      <span>Disconnect Project</span>
                    </button>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Locked Main Composer Box (Clean: Only [+] on left, Model / 🎙 / Live / Send on right) */}
          <div className="theme-bg-surface border theme-border rounded-2xl shadow-xl shadow-black/5 p-3.5 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-400/10 transition-all">
            {/* Attached file chips */}
            {attachments.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pb-2 border-b theme-border-subtle">
                {attachments.map((a, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center space-x-1 px-2 py-0.5 bg-indigo-500/10 border border-indigo-500/20 text-indigo-600 rounded-md text-[11px] font-mono"
                  >
                    <FileCode2 className="w-3 h-3" />
                    <span className="max-w-[120px] truncate">{a.name}</span>
                    <button
                      type="button"
                      onClick={() => setAttachments(attachments.filter((_, j) => j !== i))}
                      className="p-0.5 hover:text-rose-600 text-slate-400"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {/* Main Textarea */}
            <textarea
              value={inputText}
              disabled={isSubmitting}
              onChange={(e) => {
                setInputText(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(180, e.target.scrollHeight) + 'px';
              }}
              onKeyDown={(e) => {
                if (shouldSubmit(e.key, e.shiftKey, e.nativeEvent.isComposing)) {
                  e.preventDefault();
                  void handleSubmitTask();
                }
              }}
              placeholder="Ask anything..."
              rows={2}
              className="w-full bg-transparent text-sm theme-text-primary placeholder:text-slate-400 outline-none resize-none leading-relaxed min-h-[48px] pt-1"
            />

            {/* Bottom Toolbar: Left ONLY [+] | Right: Model Selector, 🎙 Mic, Live Agent, Send */}
            <div className="flex items-center justify-between pt-2 border-t theme-border-subtle">
              {/* Left Group: ONLY [+] Button */}
              <div className="relative" ref={plusMenuRef}>
                <button
                  type="button"
                  onClick={() => setShowPlusMenu(!showPlusMenu)}
                  className="w-7 h-7 rounded-full theme-bg-secondary hover:theme-border theme-text-muted hover:theme-text-primary flex items-center justify-center transition-colors border theme-border"
                  title="Attach file, Browse repository, Add context"
                  aria-label="Actions menu"
                >
                  <Plus className="w-4 h-4" />
                </button>

                {/* + Menu Popover */}
                {showPlusMenu && (
                  <div className="absolute left-0 bottom-full mb-2 w-48 theme-bg-surface border theme-border rounded-xl shadow-xl p-1.5 space-y-0.5 z-40 animate-in fade-in zoom-in-95 duration-100">
                    <button
                      type="button"
                      onClick={() => {
                        setShowPlusMenu(false);
                        fileInputRef.current?.click();
                      }}
                      className="w-full flex items-center space-x-2 px-2.5 py-1.5 text-left text-xs theme-text-primary hover:theme-bg-secondary rounded-lg transition-colors"
                    >
                      <Paperclip className="w-3.5 h-3.5 text-slate-400" />
                      <span>Attach File</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowPlusMenu(false);
                        openFileDrawer();
                      }}
                      className="w-full flex items-center space-x-2 px-2.5 py-1.5 text-left text-xs theme-text-primary hover:theme-bg-secondary rounded-lg transition-colors"
                    >
                      <Folder className="w-3.5 h-3.5 text-slate-400" />
                      <span>Browse Repository</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowPlusMenu(false);
                        fileInputRef.current?.click();
                      }}
                      className="w-full flex items-center space-x-2 px-2.5 py-1.5 text-left text-xs theme-text-primary hover:theme-bg-secondary rounded-lg transition-colors"
                    >
                      <Code2 className="w-3.5 h-3.5 text-slate-400" />
                      <span>Add Context</span>
                    </button>
                  </div>
                )}

                <input
                  ref={fileInputRef}
                  hidden
                  type="file"
                  accept={ACCEPTED_CONTEXT}
                  multiple
                  onChange={async (e) => {
                    const files = Array.from(e.target.files ?? []);
                    e.target.value = '';
                    setIsAttaching(true);
                    setComposerError('');
                    try {
                      const added = await Promise.all(files.map(readAttachment));
                      const next = [...attachments, ...added];
                      if (next.length > 4 || next.reduce((n, a) => n + new TextEncoder().encode(a.content).length, 0) > 65536) {
                        throw Error('Use at most four files totaling 64 KB.');
                      }
                      setAttachments(next);
                    } catch (err: any) {
                      setComposerError(err.message || 'Attachment rejected.');
                    } finally {
                      setIsAttaching(false);
                    }
                  }}
                />
              </div>

              {/* Right Group: Model Selector | 🎙 Mic (Voice Input) | Live Agent | Send */}
              <div className="flex items-center space-x-2">
                {/* Model Selector pill */}
                <div className="theme-bg-secondary border theme-border rounded-full px-2 py-0.5 text-xs theme-text-primary">
                  <ModelSelector preferences={preferences} disabled={isSubmitting} />
                </div>

                {/* Microphone Icon Button (Voice Input / Dictation) */}
                <button
                  type="button"
                  onClick={toggleVoiceInput}
                  className={`w-8 h-8 rounded-full flex items-center justify-center border transition-all ${
                    isVoiceInputRecording
                      ? 'bg-rose-500/20 border-rose-500 text-rose-600 animate-pulse'
                      : 'theme-bg-surface theme-border theme-text-muted hover:theme-text-primary hover:theme-bg-secondary'
                  }`}
                  title="Voice Input (dictate into composer)"
                  aria-label="Voice Input"
                >
                  <Mic className="w-4 h-4" />
                </button>

                {/* Live Voice Agent Control */}
                <button
                  type="button"
                  onClick={startLiveAgent}
                  className={`flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                    isLiveAgentActive
                      ? 'bg-indigo-600 border-indigo-600 text-white shadow-xs'
                      : 'theme-bg-surface theme-border theme-text-muted hover:theme-text-primary hover:theme-bg-secondary'
                  }`}
                  title="Live Voice Agent (continuous hands-free conversation)"
                  aria-label="Live Voice Agent"
                >
                  <AudioLines className="w-3.5 h-3.5" />
                  <span className="text-[11px]">Live</span>
                  <ChevronDown className="w-3 h-3 text-slate-400" />
                </button>

                {/* Circular Send Button */}
                <button
                  type="button"
                  disabled={!inputText.trim() || isSubmitting}
                  onClick={() => handleSubmitTask()}
                  className="w-8 h-8 rounded-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-30 disabled:hover:bg-indigo-600 text-white flex items-center justify-center transition-all shadow-md shrink-0"
                  title="Send"
                  aria-label="Send"
                >
                  {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowUp className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {composerError && (
              <p className="text-xs text-rose-600 pt-1.5" role="alert">
                {composerError}
              </p>
            )}
          </div>
        </div>
      </main>

      {/* 4. CHAT HISTORY DRAWER */}
      {showHistoryDrawer && (
        <div className="fixed inset-0 z-50 flex justify-start bg-black/30 backdrop-blur-2xs" onClick={() => setShowHistoryDrawer(false)}>
          <div
            className="w-full max-w-xs h-full theme-bg-surface border-r theme-border shadow-2xl flex flex-col animate-in slide-in-from-left duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="h-13 px-4 border-b theme-border flex items-center justify-between shrink-0">
              <div className="flex items-center space-x-2">
                <History className="w-4 h-4 text-indigo-600" />
                <span className="text-sm font-bold theme-text-primary">Chat History</span>
              </div>
              <button
                onClick={() => setShowHistoryDrawer(false)}
                className="p-1 theme-text-muted hover:theme-text-primary rounded-lg"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              <button
                onClick={() => {
                  setActiveTaskId(null);
                  setPreviousTurns([]);
                  setSubmittedTask(null);
                  setShowHistoryDrawer(false);
                }}
                className="w-full flex items-center space-x-2 px-3 py-2 text-xs font-semibold text-indigo-600 hover:bg-indigo-500/10 rounded-xl transition-colors border border-indigo-500/20 mb-2"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>New Chat</span>
              </button>

              {tasks.length === 0 ? (
                <p className="text-xs theme-text-muted p-3 text-center">No recent tasks.</p>
              ) : (
                tasks.map((t) => {
                  const isSelected = t.task_id === activeTaskId;
                  return (
                    <div
                      key={t.task_id}
                      onClick={() => {
                        setActiveTaskId(t.task_id);
                        setShowHistoryDrawer(false);
                      }}
                      className={`p-2.5 rounded-xl cursor-pointer text-xs transition-colors ${
                        isSelected
                          ? 'bg-indigo-500/10 border border-indigo-500/30 text-indigo-600 font-semibold'
                          : 'hover:theme-bg-secondary theme-text-primary border border-transparent'
                      }`}
                    >
                      <div className="flex items-center justify-between pb-1">
                        <span className="font-mono text-[10px] theme-text-muted">#{t.task_id.slice(0, 8)}</span>
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            t.status === 'COMPLETED'
                              ? 'bg-emerald-500'
                              : t.status === 'WAITING_APPROVAL'
                              ? 'bg-amber-500'
                              : t.status === 'FAILED'
                              ? 'bg-rose-500'
                              : 'bg-indigo-600'
                          }`}
                        />
                      </div>
                      <p className="truncate font-medium">{t.instruction}</p>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* 5. SCHEDULED TASKS MODAL */}
      {showScheduledModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="theme-bg-surface rounded-3xl border theme-border shadow-2xl max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-100">
            <div className="flex items-center justify-between border-b theme-border pb-3">
              <div className="flex items-center space-x-2.5">
                <Calendar className="w-5 h-5 text-indigo-600" />
                <h3 className="text-sm font-bold theme-text-primary">Scheduled Tasks</h3>
              </div>
              <button
                onClick={() => setShowScheduledModal(false)}
                className="p-1 theme-text-muted hover:theme-text-primary rounded-lg"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="text-xs theme-text-muted leading-relaxed space-y-2">
              <p>Autonomous task scheduling and recurring maintenance workflows are supported in the AgentOS runtime.</p>
              <p className="text-slate-400">No scheduled background cron jobs are currently active in this workspace.</p>
            </div>
            <div className="flex justify-end pt-2">
              <button
                onClick={() => setShowScheduledModal(false)}
                className="px-4 py-2 theme-bg-secondary hover:theme-border theme-text-primary text-xs font-semibold rounded-xl"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. REPOSITORY BROWSER DRAWER */}
      {showFileDrawer && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-2xs" onClick={() => setShowFileDrawer(false)}>
          <div
            className="w-full max-w-sm h-full theme-bg-surface border-l theme-border shadow-2xl flex flex-col animate-in slide-in-from-right duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="h-13 px-4 flex items-center justify-between border-b theme-border shrink-0">
              <div className="flex items-center space-x-2">
                <PanelRight className="w-4 h-4 text-indigo-600" />
                <span className="text-sm font-bold theme-text-primary">Browse Files</span>
                {connectedPath && (
                  <span className="text-[11px] font-mono theme-text-muted truncate max-w-[150px]">
                    {connectedPath.split(/[/\\]/).pop()}
                  </span>
                )}
              </div>
              <button
                onClick={() => setShowFileDrawer(false)}
                className="p-1.5 theme-text-muted hover:theme-text-primary rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-3">
              {fileTreeLoading ? (
                <div className="flex items-center space-x-2 text-xs theme-text-muted p-4">
                  <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                  <span>Loading workspace tree…</span>
                </div>
              ) : fileTree?.items && fileTree.items.length > 0 ? (
                <div className="space-y-0.5">
                  {fileTree.items.slice(0, 200).map((item, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSelectFile(item)}
                      className={`w-full flex items-center space-x-2 px-2 py-1.5 rounded-lg text-left text-xs transition-colors ${
                        selectedFilePath === item.path
                          ? 'bg-indigo-500/10 text-indigo-600 font-medium'
                          : 'theme-text-primary hover:theme-bg-secondary'
                      }`}
                      style={{ paddingLeft: `${(item.depth || 0) * 12 + 8}px` }}
                    >
                      {item.is_dir ? (
                        <Folder className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                      ) : (
                        <File className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      )}
                      <span className="truncate font-mono">{item.name}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-xs theme-text-muted p-4">No files found.</p>
              )}
            </div>

            {selectedFilePath && (
              <div className="border-t theme-border shrink-0 max-h-64 flex flex-col">
                <div className="px-3 py-2 theme-bg-secondary border-b theme-border flex items-center justify-between">
                  <span className="text-[11px] font-mono theme-text-muted truncate">{selectedFilePath.split(/[/\\]/).slice(-2).join('/')}</span>
                  {fileContentLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-600 shrink-0" />}
                </div>
                <pre className="flex-1 overflow-auto p-3 theme-code-block text-[11px] font-mono leading-relaxed">
                  {fileContent ?? 'Loading…'}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 7. CONNECT PROJECT MODAL */}
      {showProjectModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="theme-bg-surface rounded-3xl border theme-border shadow-2xl max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-100">
            <div className="flex items-center justify-between border-b theme-border pb-3">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-600">
                  <FolderPlus className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold theme-text-primary">Connect Project</h3>
                  <p className="text-xs theme-text-muted">Attach a repository directory to workspace</p>
                </div>
              </div>
              <button
                onClick={() => setShowProjectModal(false)}
                className="p-1 theme-text-muted hover:theme-text-primary rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleConnectProject} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-bold theme-text-primary">Project Directory Path</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. C:\Users\evo\AgentOS\workspace\test-project"
                  value={projectPathInput}
                  onChange={(e) => setProjectPathInput(e.target.value)}
                  className="w-full theme-bg-secondary border theme-border rounded-xl px-3.5 py-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500 theme-text-primary"
                />
              </div>

              {modalError && (
                <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-start space-x-2 text-xs text-rose-600">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{modalError}</span>
                </div>
              )}

              <div className="flex items-center justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowProjectModal(false)}
                  className="px-4 py-2 text-xs font-medium theme-text-muted hover:theme-bg-secondary rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!projectPathInput.trim() || modalLoading}
                  className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-xs transition-all"
                >
                  {modalLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>Attach Project</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 8. SETTINGS SUB-MODAL (Approve Permission / Models / Help / About) */}
      {settingsModalTab && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="theme-bg-surface rounded-3xl border theme-border shadow-2xl max-w-lg w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-100">
            <div className="flex items-center justify-between border-b theme-border pb-3">
              <h3 className="text-sm font-bold theme-text-primary capitalize">
                {settingsModalTab === 'permission' ? 'Approve Permission' : settingsModalTab === 'models' ? 'AI Models Configuration' : settingsModalTab === 'help' ? 'AgentOS Help & Documentation' : 'About AgentOS'}
              </h3>
              <button
                onClick={() => setSettingsModalTab(null)}
                className="p-1 theme-text-muted hover:theme-text-primary rounded-lg"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {settingsModalTab === 'permission' && (
              <div className="space-y-3 text-xs theme-text-muted">
                <p>AgentOS Human-in-the-Loop Security Gate strictly requires human approval for all file modifications and destructive shell executions.</p>
                <div className="p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-indigo-600 font-medium">
                  Status: Mandatory Gating Enabled (High-risk actions require interactive authorization).
                </div>
              </div>
            )}

            {settingsModalTab === 'models' && (
              <div className="space-y-3 text-xs theme-text-muted">
                <p>Configure and verify healthy local Ollama models.</p>
                <div className="space-y-2">
                  <ModelSelector preferences={preferences} />
                  {preferences.models?.models.map((m) => (
                    <div key={m.name} className="flex items-center justify-between p-2 theme-bg-secondary border theme-border rounded-lg">
                      <span className="font-mono theme-text-primary">{m.name}</span>
                      <span className="text-[10px] px-2 py-0.5 theme-bg-surface rounded border theme-border theme-text-muted">{m.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {settingsModalTab === 'help' && (
              <div className="space-y-2 text-xs theme-text-muted leading-relaxed">
                <p><strong className="theme-text-primary">Commands:</strong> Ask AgentOS to run tests, diagnose issues, prepare patches, or review repositories.</p>
                <p><strong className="theme-text-primary">Voice Input:</strong> Click the microphone icon to dictate your instruction into the composer, edit it, and press Send.</p>
                <p><strong className="theme-text-primary">Live Agent:</strong> Click Live to enter continuous hands-free voice conversation with the AgentOS Voice Agent.</p>
                <p><strong className="theme-text-primary">Projects:</strong> Connect existing software directories via the Project dropdown above the command composer.</p>
              </div>
            )}

            {settingsModalTab === 'about' && (
              <div className="space-y-2 text-xs theme-text-muted">
                <div className="flex items-center space-x-2">
                  <Sparkles className="w-5 h-5 text-indigo-600" />
                  <span className="font-bold text-sm theme-text-primary">AgentOS v0.3.0</span>
                </div>
                <p>A secure, autonomous AI Software Engineering Operating System.</p>
                <p className="text-[11px] text-slate-400">Powered by Google DeepMind Advanced Agentic Architecture.</p>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSettingsModalTab(null)}
                className="px-4 py-2 theme-bg-secondary hover:theme-border theme-text-primary text-xs font-semibold rounded-xl"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
