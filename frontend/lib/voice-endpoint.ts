/** Local end-of-utterance detection. A timeout always discards the recording. */
export class VoiceEndpoint {
  private speechMs = 0;
  private previous: number;
  private lastSound: number;
  public heardSpeech = false;
  constructor(private started: number) {
    this.previous = started;
    this.lastSound = started;
  }
  sample(rms: number, now: number): 'listen' | 'finish' | 'discard' {
    if (now - this.started >= 60000) return 'discard';
    if (rms > 0.02) {
      this.speechMs += Math.min(now - this.previous, 100);
      this.lastSound = now;
      if (this.speechMs >= 250) this.heardSpeech = true;
    }
    this.previous = now;
    if (this.heardSpeech && now - this.lastSound >= 1400) return 'finish';
    if (!this.heardSpeech && now - this.started >= 12000) return 'discard';
    return 'listen';
  }
}
