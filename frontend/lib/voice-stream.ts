export class VoicePlayback {
  epoch = 0;
  userSpeaking = false;
  private turns = new Map<number, number>();
  private finals = new Set<number>();
  constructor(private cancel: () => void) {}
  begin() { this.epoch++; this.userSpeaking = false; this.turns.clear(); this.finals.clear(); this.cancel(); }
  speechStarted() { this.epoch++; this.userSpeaking = true; this.cancel(); }
  final(order?: number) {
    if (order !== undefined && this.finals.has(order)) return;
    this.userSpeaking = false;
    if (order !== undefined) {
      this.finals.add(order);
      if (!this.turns.has(order)) this.turns.set(order, this.epoch);
    }
  }
  processing(order: number) { if (!this.turns.has(order)) this.turns.set(order, this.epoch); }
  canSpeak(order: number) {
    const epoch = this.turns.get(order); this.turns.delete(order);
    return !this.userSpeaking && epoch === this.epoch;
  }
}
export function reconnectDelay(attempt: number, retryable: boolean) {
  return retryable && attempt < 2 ? 1000 * 2 ** attempt : null;
}
export function supervisorStage(status: string, events: {event_type: string; payload?: Record<string, unknown>}[]) {
  const terminal: Record<string, string> = {COMPLETED: 'Completed', FAILED: 'Failed', CANCELLED: 'Cancelled', WAITING_APPROVAL: 'Awaiting approval', PLANNING: 'Planning', REVIEWING: 'Reviewing'};
  if (terminal[status]) return terminal[status];
  const latest = [...events].reverse().find(e => e.event_type === 'SUBTASK_STARTED');
  const stages: Record<string, string> = {CODING: 'Implementing', TESTING: 'Running tests', DEBUGGER: 'Investigating failure', REVIEWER: 'Reviewing', RESEARCH: 'Analyzing repository'};
  return stages[String(latest?.payload?.agent).toUpperCase()] || 'Planning';
}
