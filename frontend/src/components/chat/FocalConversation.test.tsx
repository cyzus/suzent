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

it('keeps sent Regent bubbles visible after tool work and hides delivery plumbing', () => {
  const html = renderToStaticMarkup(
    <AssistantMessage
      conversational
      regent
      message={{
        role: 'assistant',
        content: '',
        parts: [
          {
            type: 'tool',
            toolName: 'send_message',
            toolCallId: 'sent',
            state: 'completed',
            output: JSON.stringify({
              success: true,
              message: 'Delivered',
              metadata: { regent_messages: ['Looking now.', 'Two tests failed.'] },
            }),
          },
          {
            type: 'tool',
            toolName: 'web_search',
            toolCallId: 'search',
            state: 'completed',
            output: 'result',
          },
          { type: 'text', text: 'Shall I fix them?' },
        ],
      }}
      messageIndex={1}
      isStreaming={false}
      isLastMessage={false}
    />
  );
  expect(html).toContain('Looking now.');
  expect(html).toContain('Two tests failed.');
  expect(html).toContain('Shall I fix them?');
  expect(html.match(/class="regent-message-bubble"/g)).toHaveLength(3);
  expect(html).not.toContain('send_message');
  expect(html).not.toContain('Delivered');
});

it('does not leave an empty Regent card after a reaction-only reply', () => {
  const html = renderToStaticMarkup(
    <AssistantMessage
      conversational
      regent
      message={{
        role: 'assistant',
        content: '',
        parts: [
          {
            type: 'tool',
            toolName: 'react_to_message',
            state: 'completed',
            output: JSON.stringify({
              success: true,
              metadata: { regent_reaction: '👍' },
            }),
          },
        ],
      }}
      messageIndex={1}
      isStreaming={false}
      isLastMessage={false}
    />
  );
  expect(html).toBe('');
});

it('keeps long answers in bubbles with a compact identity and activity row', () => {
  const html = renderToStaticMarkup(
    <AssistantMessage
      conversational
      regent
      message={{
        role: 'assistant',
        content: '',
        parts: [
          {
            type: 'tool',
            toolName: 'web_search',
            toolCallId: 'search',
            state: 'completed',
            output: 'result',
          },
          {
            type: 'text',
            text: '## Findings\n\nA detailed explanation with structure.\n\n- First point\n- Second point',
          },
        ],
      }}
      workedDurationSeconds={35}
      messageIndex={1}
      isStreaming={false}
      isLastMessage={false}
    />
  );
  expect(html).toContain('regent-message-bubble');
  expect(html).not.toContain('regent-message-reading');
  expect(html.match(/class="regent-turn-header"/g)).toHaveLength(1);
  expect(html).toContain('regent-activity-toggle');
  expect(html).not.toContain('class="activity-rail-header activity-turn-duration"');
  expect(html).toContain('aria-expanded="false"');
});

it.each([false, true])(
  'hides quiet-only Regent replies without an empty bubble (structured: %s)',
  (structured) => {
    const html = renderToStaticMarkup(
      <AssistantMessage
        conversational
        regent
        message={{
          role: 'assistant',
          content: 'HEARTBEAT_OK',
          parts: structured ? [{ type: 'text', text: 'HEARTBEAT_OK' }] : undefined,
        }}
        messageIndex={1}
        isStreaming={false}
        isLastMessage={false}
      />
    );
    expect(html).toBe('');
  }
);
