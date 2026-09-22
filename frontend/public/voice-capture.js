import { Pcm16Encoder } from './voice-pcm.mjs';
class VoiceCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.encoder = new Pcm16Encoder(sampleRate, frame => this.port.postMessage(frame, [frame]));
  }
  process(inputs) {
    this.encoder.push(inputs[0] || []);
    return true; // Output remains silent; microphone never feeds the speakers.
  }
}
registerProcessor('agentos-voice-capture', VoiceCapture);
