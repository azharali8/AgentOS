/** Browser-native playback; only start/end events establish Speaking state. */
export class BrowserSpeech {
  private current: SpeechSynthesisUtterance | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  constructor(private synth: SpeechSynthesis,
    private create: (text: string) => SpeechSynthesisUtterance,
    private state: (speaking: boolean) => void,
    private failed: (message: string) => void,
    private started: (text: string) => void) {}
  stop() {
    this.current = null;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.synth.cancel();
    this.state(false);
  }
  speak(text: string) {
    this.stop();
    const content = text.trim().slice(0, 1800);
    if (!content) return;
    const utterance = this.create(content);
    this.current = utterance; // Retain until end; stale callbacks cannot change UI.
    const finish = (error = false) => {
      if (this.current !== utterance) return;
      this.stop();
      if (error) this.failed('Speech playback did not finish. Read the response or use Test speaker; task execution is unaffected.');
    };
    const voices = this.synth.getVoices();
    const voice = voices.find(v => v.localService && v.lang.startsWith('en')) || voices.find(v => v.default);
    if (voice) { utterance.voice = voice; utterance.lang = voice.lang; }
    utterance.onstart = () => {
      if (this.current !== utterance) return;
      if (this.timer) clearTimeout(this.timer);
      this.state(true); this.started(content);
      this.timer = setTimeout(() => finish(true), Math.min(120000, Math.max(15000, content.length * 100)));
    };
    utterance.onend = () => finish();
    utterance.onerror = () => finish(true);
    this.timer = setTimeout(() => finish(true), 5000);
    try {
      if (this.synth.paused) this.synth.resume();
      this.synth.speak(utterance);
    } catch { finish(true); }
  }
}
