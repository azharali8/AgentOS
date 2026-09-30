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

/** Speak only concise lifecycle and captured test evidence, never logs or diffs. */
export function spokenTaskResult(status: string, events: {event_type:string;payload?:Record<string,any>}[]): string {
  if(status==='WAITING_APPROVAL')return 'The changes are ready for your approval. Review the diff and click Approve and Apply.';
  if(status==='PAUSED')return 'The task is paused. Check the conversation for the next action.';
  if(status==='FAILED')return 'The task failed. The failure details are in the conversation.';
  if(status==='CANCELLED')return 'The task was cancelled.';
  const report=[...events].reverse().find(e=>e.event_type==='TEST_COMPLETED')?.payload?.report;
  if(status==='COMPLETED' && report?.passed===true && Number.isInteger(report.passed_count))
    return `The task completed successfully. ${report.passed_count} ${report.passed_count===1?'test passed':'tests passed'}.`;
  return status==='COMPLETED'?'The task completed. The result is in the conversation.':'Working on it.';
}
