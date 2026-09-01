import {
  Task,
  AgentDefinition,
  SystemHealth,
  SystemReadiness,
  TaskEvent,
  ApprovalRequestItem,
  WorkspaceTreeResponse,
  WorkspaceFileResponse,
  ModelsStatusResponse,
  LoginResponse,
  UserProfile,
} from '../types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export class AgentOSClient {
  private apiKey?: string;

  constructor(apiKey?: string) {
    this.apiKey = apiKey;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };
    if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }

    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    if (!res.ok) {
      const errorText = await res.text();
      let message = errorText;
      try {
        const json = JSON.parse(errorText);
        if (json.detail) message = json.detail;
      } catch {}
      throw new Error(`API Error (${res.status}): ${message}`);
    }

    return res.json();
  }

  // Authentication
  async login(email: string, password: string): Promise<LoginResponse> {
    return this.request<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async getProfile(): Promise<UserProfile> {
    return this.request<UserProfile>('/api/v1/auth/me');
  }

  async logout(): Promise<void> {
    try {
      await this.request('/api/v1/auth/logout', { method: 'POST' });
    } catch {}
  }

  // System & Models
  async getHealth(): Promise<SystemHealth> {
    return this.request<SystemHealth>('/api/v1/system/health');
  }

  async getReadiness(): Promise<SystemReadiness> {
    return this.request<SystemReadiness>('/api/v1/system/readiness');
  }

  async getModels(): Promise<ModelsStatusResponse> {
    return this.request<ModelsStatusResponse>('/api/v1/system/models');
  }

  async getSystemMetrics(): Promise<any> {
    return this.request<any>('/api/v1/system/metrics');
  }

  // Tasks
  async createTask(
    task: string,
    priority: number = 1,
    options: { requested_agent?: string; execution_mode?: string; sync?: boolean } = {}
  ): Promise<Task> {
    return this.request<Task>('/api/v1/tasks', {
      method: 'POST',
      body: JSON.stringify({
        task,
        priority,
        requested_agent: options.requested_agent,
        execution_mode: options.execution_mode || 'autonomous',
        sync: options.sync ?? false,
      }),
    });
  }

  async listTasks(limit: number = 50, offset: number = 0): Promise<Task[]> {
    return this.request<Task[]>(`/api/v1/tasks?limit=${limit}&offset=${offset}`);
  }

  async getTask(taskId: string): Promise<Task> {
    return this.request<Task>(`/api/v1/tasks/${taskId}`);
  }

  async getTaskStatus(taskId: string): Promise<any> {
    return this.request<any>(`/api/v1/tasks/${taskId}/status`);
  }

  async getTaskResult(taskId: string): Promise<any> {
    return this.request<any>(`/api/v1/tasks/${taskId}/result`);
  }

  async getTaskEvents(taskId: string): Promise<TaskEvent[]> {
    return this.request<TaskEvent[]>(`/api/v1/tasks/${taskId}/events`);
  }

  async cancelTask(taskId: string): Promise<any> {
    return this.request<any>(`/api/v1/tasks/${taskId}/cancel`, {
      method: 'POST',
    });
  }

  async getTaskArtifacts(taskId: string): Promise<any[]> {
    return this.request<any[]>(`/api/v1/tasks/${taskId}/artifacts`);
  }

  // Approvals (Human-in-the-Loop)
  async listApprovals(limit: number = 50, offset: number = 0): Promise<ApprovalRequestItem[]> {
    return this.request<ApprovalRequestItem[]>(`/api/v1/approvals?limit=${limit}&offset=${offset}`);
  }

  async getApproval(approvalId: string): Promise<ApprovalRequestItem> {
    return this.request<ApprovalRequestItem>(`/api/v1/approvals/${approvalId}`);
  }

  async resolveApproval(approvalId: string, approved: boolean, reason?: string): Promise<any> {
    return this.request<any>(`/api/v1/approvals/${approvalId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ approved, reason }),
    });
  }

  // Workspace Explorer
  async getWorkspaceTree(subpath: string = ''): Promise<WorkspaceTreeResponse> {
    return this.request<WorkspaceTreeResponse>(`/api/v1/workspace/tree?subpath=${encodeURIComponent(subpath)}`);
  }

  async getWorkspaceFile(path: string): Promise<WorkspaceFileResponse> {
    return this.request<WorkspaceFileResponse>(`/api/v1/workspace/file?path=${encodeURIComponent(path)}`);
  }

  async getWorkspaceInfo(): Promise<any> {
    return this.request<any>('/api/v1/workspace/info');
  }

  async setWorkspaceRoot(path: string, name: string = ''): Promise<any> {
    return this.request<any>('/api/v1/workspace/set-root', {
      method: 'POST',
      body: JSON.stringify({ path, name }),
    });
  }

  async createNewProject(
    name: string,
    location: string,
    instruction: string,
    autoStartTask: boolean = true
  ): Promise<any> {
    return this.request<any>('/api/v1/workspace/create-project', {
      method: 'POST',
      body: JSON.stringify({
        name,
        location,
        instruction,
        auto_start_task: autoStartTask,
      }),
    });
  }

  // Agents
  async listAgents(): Promise<AgentDefinition[]> {
    return this.request<AgentDefinition[]>('/api/v1/agents');
  }

  async getAgent(agentId: string): Promise<AgentDefinition> {
    return this.request<AgentDefinition>(`/api/v1/agents/${agentId}`);
  }

  async getAgentCapabilities(agentId: string): Promise<string[]> {
    return this.request<string[]>(`/api/v1/agents/${agentId}/capabilities`);
  }

  async getAgentMetrics(agentId: string): Promise<any> {
    return this.request<any>(`/api/v1/agents/${agentId}/metrics`);
  }

  async invokeAgent(agentId: string, instruction: string, targetFiles: string[] = [], context: Record<string, any> = {}): Promise<any> {
    return this.request<any>(`/api/v1/agents/${agentId}/invoke`, {
      method: 'POST',
      body: JSON.stringify({ instruction, target_files: targetFiles, context }),
    });
  }

  // System Queue & Workers
  async getSystemQueue(): Promise<any> {
    return this.request<any>('/api/v1/system/queue');
  }

  async getSystemWorkers(): Promise<any> {
    return this.request<any>('/api/v1/system/workers');
  }

  // Evaluations
  async getEvaluations(): Promise<any> {
    return this.request<any>('/api/v1/evaluations/benchmarks');
  }
}
