/** Built-in voice suggestions; custom deployments keep an explicit ID override. */
export interface SpeechModelOptions {
  voices: string[];
  formats: string[];
  speed: boolean;
  instructions: boolean;
}
const formats = ['auto', 'mp3', 'wav', 'opus', 'aac', 'flac'];
// https://ai.google.dev/gemini-api/docs/speech-generation#voice-options
const geminiVoices = [
  'Zephyr',
  'Puck',
  'Charon',
  'Kore',
  'Fenrir',
  'Leda',
  'Orus',
  'Aoede',
  'Callirrhoe',
  'Autonoe',
  'Enceladus',
  'Iapetus',
  'Umbriel',
  'Algieba',
  'Despina',
  'Erinome',
  'Algenib',
  'Rasalgethi',
  'Laomedeia',
  'Achernar',
  'Alnilam',
  'Schedar',
  'Gacrux',
  'Pulcherrima',
  'Achird',
  'Zubenelgenubi',
  'Vindemiatrix',
  'Sadachbia',
  'Sadaltager',
  'Sulafat',
];
// https://developers.openai.com/api/docs/guides/text-to-speech
const legacyVoices = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'];
export function speechModelOptions(model: string): SpeechModelOptions {
  const [provider, ...parts] = model.split('/');
  const name = parts.join('/');
  if (
    (provider === 'gemini' || provider === 'vertex_ai') &&
    name.startsWith('gemini-') &&
    name.includes('tts')
  )
    return { voices: geminiVoices, formats: ['auto', 'wav'], speed: false, instructions: true };
  if (provider === 'openai' && (name === 'tts-1' || name === 'tts-1-hd'))
    return { voices: legacyVoices, formats, speed: true, instructions: false };
  if (provider === 'openai' && name.startsWith('gpt-4o-mini-tts'))
    return {
      voices: [...legacyVoices, 'ash', 'ballad', 'coral', 'sage', 'verse', 'marin', 'cedar'],
      formats,
      speed: true,
      instructions: true,
    };
  return { voices: [], formats, speed: true, instructions: true };
}

export function resetSpeechForModel<
  T extends { voice: string; response_format: string; speed: number; instructions: string },
>(settings: T, model: string): T {
  const options = speechModelOptions(model);
  return {
    ...settings,
    voice: '',
    response_format: options.formats.includes(settings.response_format)
      ? settings.response_format
      : 'auto',
    speed: options.speed ? settings.speed : 1,
    instructions: options.instructions ? settings.instructions : '',
  };
}
