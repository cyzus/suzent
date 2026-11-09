import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChatInputPanel } from './ChatInputPanel';
import type { ChatConfig } from '../types/api';
import type { VoiceSession } from '../hooks/useVoiceSession';

vi.mock('../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock('../hooks/useAcpAgents', () => ({ useAcpAgents: () => [] }));
vi.mock('../hooks/useSlashCommands', () => ({ useSlashCommands: () => [] }));
vi.mock('./chat/MentionTextArea', () => ({
  MentionTextArea: React.forwardRef<unknown, { className?: string; style?: React.CSSProperties }>(
    ({ className, style }, _ref) => <div className={className} style={style} />
  ),
}));

const idleVoice: VoiceSession = {
  status: 'idle',
  active: false,
  transcripts: [],
  working: false,
  liveCaptions: null,
  errorKey: null,
  playing: false,
  supported: true,
  micLevel: { current: 0 },
  start: () => {},
  stop: () => {},
  interrupt: () => {},
};

function renderComposer(): string {
  vi.stubGlobal('navigator', { userAgent: '', platform: '' });
  return renderToStaticMarkup(
    <ChatInputPanel
      currentChatId="regular"
      input=""
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
      voice={idleVoice}
    />
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('composer editor cap in the input panel', () => {
  it('caps the editor with a max height and keeps it scrolling and compact', () => {
    const html = renderComposer();
    expect(html).toContain('max-height:360px');
    expect(html).toContain('min-h-[40px]');
    expect(html).toContain('overflow-y-auto');
    expect(html).not.toContain('max-h-[120px]');
    expect(html).toContain('chatInput.attachFiles');
    expect(html).toContain('chatInput.sendMessage');
  });
});
