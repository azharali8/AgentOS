export type UserRole = 'ADMIN' | 'DEVELOPER' | 'USER' | 'VIEWER';

export interface UserProfile {
  user_id: string;
  username: string;
  email: string;
  role: UserRole;
  is_authenticated: boolean;
}

export interface LoginResponse {
  token: string;
  user_id: string;
  username: string;
  email: string;
  role: UserRole;
  message: string;
}

export interface Task {
  task_id: string;
  status: 'PENDING' | 'PLANNING' | 'RUNNING' | 'EXECUTING' | 'REVIEWING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'WAITING_APPROVAL';
  instruction: string;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
  result_summary?: string;
  error?: string;
  priority?: number;
  assigned_agent?: string;
  approval_id?: string;
  metadata?: Record<string, any>;
}

export interface AgentDefinition {
  name: string;
  agent_type: string;
  description: string;
  capabilities: string[];
  allowed_tools: string[];
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
  max_concurrency: number;
  max_execution_time: number;
}

export interface TaskEvent {
  event_id: string;
  task_id: string;
  event_type: string;
  timestamp: string;
  step_id?: string;
  payload?: Record<string, any>;
}

export interface ApprovalRequestItem {
  approval_id: string;
  task_id: string;
  step_id: string;
  tool_name: string;
  operation: string;
  arguments_hash: string;
  arguments_summary: Record<string, any>;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
  reason: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED';
  requested_at: string;
  resolved_at?: string;
  resolved_by?: string;
}

export interface WorkspaceItem {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  is_sensitive: boolean;
}

export interface WorkspaceTreeResponse {
  root: string;
  current_path: string;
  items: WorkspaceItem[];
}

export interface WorkspaceFileResponse {
  path: string;
  name: string;
  size: number;
  content: string;
}

export interface ModelInfo {
  name: string;
  provider: string;
  tier: 'LOCAL' | 'CLOUD';
  status: 'READY' | 'UNAVAILABLE' | 'CONFIGURED';
  endpoint: string;
  available_local_tags?: string[];
}

export interface ModelsStatusResponse {
  active_provider: string;
  configured_model: string;
  models: ModelInfo[];
}

export interface SystemHealth {
  status: string;
  version: string;
  timestamp: string;
  process: string;
}

export interface SystemReadiness {
  status: string;
  ready: boolean;
  database: string;
  security_manager: string;
  rate_limiter: string;
  agents_available: number;
  model_router: string;
}

export interface BenchmarkResultItem {
  case_id: string;
  name: string;
  passed: boolean;
  duration_seconds: number;
  error?: string | null;
}

export interface BenchmarkSuiteResult {
  total_cases: number;
  passed_count: number;
  failed_count: number;
  success_rate_pct: number;
  results: BenchmarkResultItem[];
}
