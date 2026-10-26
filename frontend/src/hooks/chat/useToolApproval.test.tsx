import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { useToolApproval } from './useToolApproval';
import type { ChatConfig } from '../../types/api';

describe('useToolApproval', () => {
  it('routes approval resume to the active chat rather than a stale suspended streamingChatIdRef', async () => {
    const resumeStream = vi.fn().mockResolvedValue(undefined);
    const setIsStreaming = vi.fn();
    let captured: ReturnType<typeof useToolApproval> | null = null;

    const Probe: React.FC = () => {
      captured = useToolApproval({
        currentChatId: 'active-chat',
        activeStreamingChatId: 'stale-suspended-chat',
        config: { model: 'm', agent: 'a', tools: [] } as ChatConfig,
        messages: [],
        streamingParts: [],
        streamingChatIdRef: { current: 'stale-suspended-chat' },
        activeChatIdRef: { current: 'active-chat' },
        retireStopAttempt: vi.fn(),
        setConfig: vi.fn(),
        updateMessage: vi.fn(),
        setIsStreaming,
        resumeStream,
        resolveApproval: vi.fn(),
        addApprovalDecision: () => true,
        consumeApprovalDecisions: () => [
          {
            approvalId: 'req-1',
            toolCallId: 'call-1',
            approved: true,
          },
        ],
      });
      return null;
    };

    renderToStaticMarkup(<Probe />);
    expect(captured).not.toBeNull();
    await captured!.handleToolApproval('req-1', 'call-1', true);

    expect(setIsStreaming).toHaveBeenCalledWith(true, 'active-chat');
    expect(resumeStream).toHaveBeenCalledTimes(1);
    expect(resumeStream.mock.calls[0][0].chat_id).toBe('active-chat');
  });
});
