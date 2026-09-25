import { expect, it } from 'vitest';
import { resetSpeechForModel, speechModelOptions } from './speechModels';

it('offers Gemini voices and only implemented Gemini controls', () => {
  for (const provider of ['gemini', 'vertex_ai']) {
    const options = speechModelOptions(`${provider}/gemini-2.5-flash-preview-tts`);
    expect(options.voices).toContain('Zephyr');
    expect(options.voices).toContain('Kore');
    expect(options.formats).toEqual(['auto', 'wav']);
    expect(options.speed).toBe(false);
    expect(options.instructions).toBe(true);
  }
});
it('distinguishes OpenAI legacy TTS from models supporting style instructions', () => {
  expect(speechModelOptions('openai/tts-1-hd').instructions).toBe(false);
  expect(speechModelOptions('openai/gpt-4o-mini-tts').voices).toContain('cedar');
  expect(speechModelOptions('openai/gpt-4o-mini-tts').instructions).toBe(true);
});
it('does not assume voice IDs or model capabilities for custom/Azure deployments', () => {
  expect(speechModelOptions('custom/gpt-4o-mini-tts').voices).toEqual([]);
  expect(speechModelOptions('azure/my-deployment').voices).toEqual([]);
});
it('resets incompatible model settings while retaining playback volume', () => {
  const previous = {
    voice: 'alloy',
    response_format: 'mp3',
    speed: 2,
    instructions: 'calm',
    volume: 0.6,
  };
  const gemini = resetSpeechForModel(previous, 'gemini/gemini-2.5-flash-preview-tts');
  expect(gemini).toEqual({ ...previous, voice: '', response_format: 'auto', speed: 1 });
  expect(resetSpeechForModel(gemini, 'openai/tts-1').instructions).toBe('');
});
