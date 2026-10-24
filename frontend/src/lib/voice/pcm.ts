export function float32ToInt16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index]));
    output[index] = sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767);
  }
  return output;
}

export function int16ToFloat32(input: Int16Array | ArrayBuffer): Float32Array<ArrayBuffer> {
  const samples = input instanceof Int16Array ? input : new Int16Array(input);
  const output = new Float32Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    output[index] = samples[index] < 0 ? samples[index] / 32768 : samples[index] / 32767;
  }
  return output;
}

export class StreamingLinearResampler {
  private readonly step: number;
  private position = 0;
  private previous: number | null = null;

  constructor(inputRate: number, outputRate: number) {
    if (inputRate <= 0 || outputRate <= 0) throw new Error('Sample rates must be positive');
    this.step = inputRate / outputRate;
  }

  process(input: Float32Array): Float32Array {
    if (!input.length) return new Float32Array();
    const source = this.previous === null ? input : Float32Array.from([this.previous, ...input]);
    const output: number[] = [];
    while (this.position + 1 < source.length) {
      const left = Math.floor(this.position);
      const fraction = this.position - left;
      output.push(source[left] + (source[left + 1] - source[left]) * fraction);
      this.position += this.step;
    }
    this.position -= source.length - 1;
    this.previous = source[source.length - 1];
    return Float32Array.from(output);
  }
}

export function rms(input: Float32Array): number {
  if (!input.length) return 0;
  let sum = 0;
  for (const sample of input) sum += sample * sample;
  return Math.sqrt(sum / input.length);
}
