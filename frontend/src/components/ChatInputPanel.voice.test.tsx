import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChatInputPanel } from './ChatInputPanel';
import type { VoiceSession, VoiceSessionStatus, VoiceTranscript } from '../hooks/useVoiceSession';
import type { ChatConfig } from '../types/api';

vi.mock('../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock('../hooks/useAcpAgents', () => ({ useAcpAgents: () => [] }));
vi.mock('../hooks/useSlashCommands', () => ({ useSlashCommands: () => [] }));
// Expose the props the composer hands the editor; the real one needs a DOM.
vi.mock('./chat/MentionTextArea', () => ({
  MentionTextArea: React.forwardRef<
    unknown,
    { value: string; disabled?: boolean; placeholder?: string }
  >(({ value, disabled, placeholder }, _ref) => (
    <div
      data-testid="editor"
      data-value={value}
      data-disabled={String(Boolean(disabled))}
      data-placeholder={placeholder}
    />
  )),
}));

afterEach(() => vi.unstubAllGlobals());

const makeVoice = (
  status: VoiceSessionStatus,
  extra: Partial<VoiceSession> = {}
): VoiceSession => ({
  status,
  active: status !== 'idle' && status !== 'error',
  transcripts: [],
  working: false,
  liveCaptions: null,
  errorKey: null,
  supported: true,
  micLevel: { current: 0 },
  start: () => {},
  stop: () => {},
  interrupt: () => {},
  ...extra,
});

const line = (
  id: string,
  speaker: VoiceTranscript['speaker'],
  text: string,
  final = true
): VoiceTranscript => ({ id, speaker, text, final });

const render = (voice: VoiceSession, input = 'typed draft'): string => {
  vi.stubGlobal('navigator', { userAgent: '', platform: '' });
  return renderToStaticMarkup(
    <ChatInputPanel
      currentChatId="regular"
      input={input}
      setInput={() => {}}
      selectedFiles={[]}
      handleFileSelect={() => {}}
      removeFile={() => {}}
      send={() => {}}
      config={{ model: 'test-model', permission_mode: 'auto' } as ChatConfig}
      setConfig={() => {}}
      fileInputRef={React.createRef<HTMLInputElement>()}
      textareaRef={React.createRef<HTMLTextAreaElement>()}
      backendConfig={null}
      configReady
      streamingForCurrentChat={false}
      voice={voice}
    />
  );
};

// Tailwind's `disabled:` classes also contain the word, so match the attribute.
const DISABLED = /\sdisabled=""/;

const button = (html: string, label: string): string => {
  const match = new RegExp(`<button[^>]*(?:title|aria-label)="${label}"[^>]*>`).exec(html);
  if (!match) throw new Error(`button not found: ${label}`);
  return match[0];
};

describe('composer with voice mode', () => {
  it('shows no voice bar when voice is off', () => {
    const html = render(makeVoice('idle'));
    expect(html).not.toContain('voice.states.');
    expect(button(html, 'voice.micButton')).not.toMatch(DISABLED);
  });

  it.each<VoiceSessionStatus>(['connecting', 'listening', 'user_speaking', 'thinking', 'speaking'])(
    'keeps the composer usable while %s',
    (status) => {
      const html = render(makeVoice(status));
      expect(html).toContain('data-value="typed draft"');
      expect(html).toContain('data-disabled="false"');
      expect(button(html, 'chatInput.sendMessage')).not.toMatch(DISABLED);
      expect(button(html, 'chatInput.attachFiles')).not.toMatch(DISABLED);
      // State is shown exactly once, in the voice bar.
      expect(html.split(`voice.states.${status}`).length - 1).toBe(1);
    }
  );

  it('captions the latest line from each speaker, not the whole call', () => {
    const html = render(
      makeVoice('listening', {
        transcripts: [
          line('s:1', 'user', 'old question'),
          line('s:2', 'assistant', 'old answer'),
          line('s:3', 'user', '今天天气怎么样', false),
          line('s:4', 'assistant', '我来查一下'),
        ],
      })
    );
    expect(html).toContain('今天天气怎么样');
    expect(html).toContain('我来查一下');
    expect(html).not.toContain('old question');
    expect(html).not.toContain('old answer');
  });

  it('says when a model only captions after the user stops', () => {
    const html = render(makeVoice('user_speaking', { liveCaptions: false }));
    expect(html).toContain('voice.captionsAfterSpeech');
    const live = render(makeVoice('user_speaking', { liveCaptions: true }));
    expect(live).not.toContain('voice.captionsAfterSpeech');
  });

  it('shows when Suzent is working and offers stop-speaking only while speaking', () => {
    expect(render(makeVoice('listening', { working: true }))).toContain('voice.working');
    expect(render(makeVoice('listening'))).not.toContain('voice.stopSpeaking');
    expect(render(makeVoice('speaking'))).toContain('voice.stopSpeaking');
  });

  it('offers exactly one way to end a live call: the bar, not the mic button', () => {
    const html = render(makeVoice('listening'));
    expect(html.split('aria-label="voice.end"').length - 1).toBe(1);
    expect(html).not.toMatch(/<button[^>]*aria-label="voice\.micButton"/);
  });

  it('draws the mic meter once the mic is live, not while connecting', () => {
    const bars = (html: string) => html.split('w-[2px] origin-center').length - 1;
    expect(bars(render(makeVoice('listening')))).toBe(8);
    expect(bars(render(makeVoice('connecting')))).toBe(0);
  });

  it('renders the bar outside the editor box its placeholder overlays cover', () => {
    const html = render(makeVoice('listening'), '');
    const bar = html.indexOf('voice.states.listening');
    const editorBox = html.indexOf('<div class="relative"><div data-testid="editor"');
    expect(bar).toBeGreaterThan(-1);
    expect(editorBox).toBeGreaterThan(bar);
  });

  it('shows the error in the bar and hands the mic back', () => {
    const html = render(makeVoice('error', { errorKey: 'voice.errors.no_api_key' }));
    expect(html).toContain('voice.errors.no_api_key');
    expect(html).toContain('data-disabled="false"');
    expect(button(html, 'voice.micButton')).not.toMatch(DISABLED);
  });
});
