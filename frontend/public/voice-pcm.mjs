// Stateful mono downsampling and little-endian PCM16 framing (100 ms at 16 kHz).
export class Pcm16Encoder {
  constructor(inputRate, emit) {
    if (inputRate < 16000) throw new Error('Microphone sample rate must be at least 16 kHz.');
    this.ratio = inputRate / 16000;
    this.emit = emit;
    this.weight = 0;
    this.sum = 0;
    this.index = 0;
    this.frame = new ArrayBuffer(3200);
    this.view = new DataView(this.frame);
  }
  push(channels) {
    if (!channels.length) return;
    for (let i = 0; i < channels[0].length; i++) {
      let sample = 0;
      for (const channel of channels) sample += channel[i] / channels.length;
      let remaining = 1;
      while (remaining > 1e-9) {
        const take = Math.min(remaining, this.ratio - this.weight);
        this.sum += sample * take;
        this.weight += take;
        remaining -= take;
        if (this.weight >= this.ratio - 1e-9) {
          const value = Math.max(-1, Math.min(1, this.sum / this.ratio));
          this.view.setInt16(this.index * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
          this.sum = 0; this.weight = 0;
          if (++this.index === 1600) {
            this.emit(this.frame);
            this.frame = new ArrayBuffer(3200); this.view = new DataView(this.frame); this.index = 0;
          }
        }
      }
    }
  }
}
