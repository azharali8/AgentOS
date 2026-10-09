'use client';
import React from 'react';
import { Plus, Folder, MessageSquare, ChevronRight, AlertCircle, RefreshCw } from 'lucide-react';
import { ProjectRecord, ConversationRecord } from '../lib/api';

export function ProjectsSidebar({
  projects,
  conversations,
  activeProject,
  activeConversation,
  busy,
  error,
  onProject,
  onConversation,
  onNewProject,
  onNewConversation,
  onRetry,
  onMoreProjects,
  onMoreConversations,
}: {
  projects: ProjectRecord[];
  conversations: ConversationRecord[];
  activeProject: string | null;
  activeConversation: string | null;
  busy: boolean;
  error: string;
  onProject: (id: string) => void;
  onConversation: (id: string) => void;
  onNewProject: () => void;
  onNewConversation: () => void;
  onRetry: () => void;
  onMoreProjects?: () => void;
  onMoreConversations?: () => void;
}) {
  return (
    <section aria-label="Projects" className="space-y-1">
      {/* Header row */}
      <div className="flex items-center justify-between px-2 py-1.5">
        <span className="text-[10px] uppercase tracking-widest font-semibold theme-text-muted">Projects</span>
        <button
          onClick={onNewProject}
          disabled={busy}
          title="New Project"
          aria-label="New Project"
          className="w-5 h-5 flex items-center justify-center rounded-md hover:theme-bg-secondary theme-text-muted hover:theme-text-primary transition-colors disabled:opacity-40"
        >
          <Plus size={13} />
        </button>
      </div>

      {/* Loading */}
      {busy && !projects.length && (
        <p role="status" className="text-[11px] px-2 py-1 theme-text-muted animate-pulse">Loading…</p>
      )}

      {/* Error */}
      {error && (
        <div role="alert" className="mx-2 px-2 py-2 rounded-lg bg-rose-500/10 border border-rose-500/20">
          <div className="flex items-start gap-1.5">
            <AlertCircle size={12} className="text-rose-500 shrink-0 mt-0.5" />
            <p className="text-[11px] text-rose-600 leading-snug">{error}</p>
          </div>
          <button
            onClick={onRetry}
            className="mt-1.5 flex items-center gap-1 text-[11px] text-rose-600 hover:text-rose-700"
          >
            <RefreshCw size={10} />
            Retry
          </button>
        </div>
      )}

      {/* Empty state */}
      {!busy && !error && !projects.length && (
        <div className="px-2 py-3">
          <p className="text-[11px] theme-text-muted leading-relaxed">
            Connect a repository to start. Conversations stay with the project.
          </p>
          <button
            onClick={onNewProject}
            className="mt-2 flex items-center gap-1.5 text-[11px] text-indigo-600 hover:text-indigo-700 font-medium"
          >
            <Plus size={11} />
            Connect project
          </button>
        </div>
      )}

      {/* Project list */}
      <div className="space-y-0.5">
        {projects.map((project) => {
          const isActive = activeProject === project.project_id;
          const projectConversations = conversations.filter(
            (c) => c.project_id === project.project_id
          );
          return (
            <div key={project.project_id}>
              <button
                disabled={busy}
                aria-expanded={isActive}
                aria-current={isActive ? 'true' : undefined}
                onClick={() => onProject(project.project_id)}
                className={`flex items-center gap-2 w-full text-left px-2 py-1.5 rounded-lg text-xs transition-colors ${
                  isActive
                    ? 'theme-bg-secondary theme-text-primary font-medium'
                    : 'theme-text-muted hover:theme-bg-secondary hover:theme-text-primary'
                } disabled:opacity-40`}
              >
                <Folder
                  size={13}
                  className={isActive ? 'text-indigo-500 shrink-0' : 'text-slate-400 shrink-0'}
                />
                <span className="truncate flex-1">{project.name}</span>
                {isActive && <ChevronRight size={11} className="text-indigo-400 shrink-0 rotate-90" />}
              </button>

              {/* Conversations under active project */}
              {isActive && (
                <div className="pl-4 mt-0.5 space-y-0.5">
                  {projectConversations.map((c) => {
                    const isActiveCon = activeConversation === c.conversation_id;
                    return (
                      <button
                        key={c.conversation_id}
                        disabled={busy}
                        aria-current={isActiveCon ? 'page' : undefined}
                        onClick={() => onConversation(c.conversation_id)}
                        className={`flex items-center gap-1.5 w-full text-left text-[11px] py-1.5 px-2 rounded-lg transition-colors ${
                          isActiveCon
                            ? 'theme-bg-secondary theme-text-primary font-medium'
                            : 'theme-text-muted hover:theme-bg-secondary hover:theme-text-primary'
                        } disabled:opacity-40`}
                      >
                        <MessageSquare
                          size={11}
                          className={isActiveCon ? 'text-indigo-400 shrink-0' : 'text-slate-400 shrink-0'}
                        />
                        <span className="truncate">{c.title}</span>
                      </button>
                    );
                  })}

                  {onMoreConversations && (
                    <button
                      disabled={busy}
                      onClick={onMoreConversations}
                      className="text-[11px] engineering-link px-2 py-1"
                    >
                      More conversations…
                    </button>
                  )}

                  <button
                    disabled={busy}
                    onClick={onNewConversation}
                    className="flex items-center gap-1 text-[11px] theme-text-muted hover:theme-text-primary px-2 py-1.5 transition-colors disabled:opacity-40"
                  >
                    <Plus size={11} />
                    New conversation
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {onMoreProjects && (
        <button
          disabled={busy}
          onClick={onMoreProjects}
          className="text-[11px] engineering-link px-2 py-1 disabled:opacity-40"
        >
          More projects…
        </button>
      )}
    </section>
  );
}
