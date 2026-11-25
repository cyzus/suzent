class VoiceCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
    this.batchSize = Math.max(128, Math.round(sampleRate * 0.03));
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (let index = 0; index < channel.length; index += 1) this.samples.push(channel[index]);
    while (this.samples.length >= this.batchSize) {
      const output = new Float32Array(this.samples.splice(0, this.batchSize));
      this.port.postMessage(output.buffer, [output.buffer]);
    }
    return true;
  }
}

registerProcessor('voice-capture', VoiceCaptureProcessor);
