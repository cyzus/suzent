import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChatInputPanel } from '../ChatInputPanel';
import { AssistantMessage } from './AssistantMessage';
import type { ChatConfig } from '../../types/api';
import type { VoiceSession } from '../../hooks/useVoiceSession';

vi.mock('../../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock('../../hooks/useAcpAgents', () => ({ useAcpAgents: () => [] }));
vi.mock('../../hooks/useSlashCommands', () => ({ useSlashCommands: () => [] }));

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

afterEach(() => vi.unstubAllGlobals());

const composer = (chatId: string): string => {
  vi.stubGlobal('navigator', { userAgent: '', platform: '' });
  return renderToStaticMarkup(
    <ChatInputPanel
      currentChatId={chatId}
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
};

const response = (conversational: boolean): string =>
  renderToStaticMarkup(
    <AssistantMessage
      conversational={conversational}
      message={{
        role: 'assistant',
        content: 'Hello',
        model: 'test-model',
        timestamp: '2026-10-19T09:30:00Z',
      }}
      messageIndex={0}
      isStreaming={false}
      isLastMessage={false}
      onRetry={() => {}}
      onFork={() => {}}
    />
  );

describe('Focal conversation controls', () => {
  it('keeps model and thinking controls while hiding only focal permission controls', () => {
    const html = composer('focal-suzent');
    expect(html).toContain('chatInput.attachFiles');
    expect(html).toContain('chatInput.sendMessage');
    expect(html).toContain('chat-composer-model');
    expect(html).toContain('suzent-ts__trigger');
    expect(html).not.toContain('chatWindow.permissionModeInputLabels');
    expect(composer('regular')).toContain('chat-composer-model');
    expect(composer('regular')).toContain('chatWindow.permissionModeInputLabels');
  });
  it.each([false, true])(
    'renders PUA citations in focal responses (structured: %s)',
    (structured) => {
      const content = 'Fact\ue200cite\ue202t0_src_1\ue201.';
      const html = renderToStaticMarkup(
        <AssistantMessage
          conversational
          message={{ role: 'assistant', content }}
          aguiParts={structured ? [{ type: 'text', text: content }] : undefined}
          chatCitationSources={
            new Map([
              [
                't0_src_1',
                { id: 't0_src_1', type: 'search', title: 'Example', url: 'https://example.com' },
              ],
            ])
          }
          messageIndex={0}
          isStreaming={false}
          isLastMessage={false}
        />
      );
      expect(html).toContain('example.com');
      expect(html).not.toContain('\ue200');
      expect(html).not.toContain('\ue202');
    }
  );
  it('keeps copy while removing retry, fork and model signature only for focal', () => {
    const focal = response(true);
    expect(focal).toContain('status.copyToClipboard');
    expect(focal).not.toContain('common.retry');
    expect(focal).not.toContain('conversationFork.button');
    expect(focal).not.toContain('test-model');
    expect(focal).not.toContain('<time');
    const regular = response(false);
    expect(regular).toContain('common.retry');
    expect(regular).toContain('conversationFork.button');
    expect(regular).toContain('test-model');
    expect(regular).toContain('<time');
  });
});
