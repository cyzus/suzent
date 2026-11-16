import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../hooks/useChatStore', () => ({
  useChatCoreStore: () => ({ currentChatId: 'chat-1', chats: [] }),
  useChatStreamingStore: () => ({ isStreaming: false, activeStreamingChatId: null }),
  useChatStore: () => ({}),
}));

import {
  HEAD_C,
  STAGE_SPECS,
  SUZENT_BODY_RING,
  SUZENT_EXPRESSIONS,
  evaluateFullBodyAct,
  resolveSuzentStage,
  springValue,
  stepSpring,
} from '../../lib/suzentBot';
import { SuzentBotMark } from './SuzentBotMark';
import { ActivityRail } from './ActivityRail';
import { AssistantMessage } from './AssistantMessage';
import { ToolGroupIcon } from './toolGroupIcon';
import { I18nProvider } from '../../i18n';

describe('SuzentBotEngine & SuzentBotMark', () => {
  it('generates the 96-point Suzent 24x24 rounded-square body and 25 expressive 48-point eye pairs', () => {
    expect(SUZENT_BODY_RING).toHaveLength(96);
    expect(SUZENT_EXPRESSIONS).toHaveLength(25);
    for (const [leftEye, rightEye] of SUZENT_EXPRESSIONS) {
      expect(leftEye).toHaveLength(48);
      expect(rightEye).toHaveLength(48);
    }
  });

  it('maps tool names and states into the expected SuzentBotStageId', () => {
    expect(resolveSuzentStage({ hasPending: true, toolName: 'run_command' })).toBe('approval');
    expect(resolveSuzentStage({ isError: true, toolName: 'write_file' })).toBe('error');
    expect(resolveSuzentStage({ isThinking: true })).toBe('thinking');
    expect(resolveSuzentStage({ toolName: 'read_file' })).toBe('reading');
    expect(resolveSuzentStage({ toolName: 'webpage_fetch' })).toBe('ingesting');
    expect(resolveSuzentStage({ toolName: 'memory_search' })).toBe('ingesting');
    expect(resolveSuzentStage({ toolName: 'edit_file' })).toBe('writing');
    expect(resolveSuzentStage({ toolName: 'web_search' })).toBe('searching');
    expect(resolveSuzentStage({ toolName: 'run_command' })).toBe('bash');
    expect(resolveSuzentStage({ toolName: 'start_command' })).toBe('starting');
    expect(resolveSuzentStage({ toolName: 'agent' })).toBe('subagent');
    expect(resolveSuzentStage({ toolName: 'render_ui' })).toBe('vision');
    expect(resolveSuzentStage({ toolName: 'skill_execute' })).toBe('skill');
    expect(resolveSuzentStage({ toolName: 'send_file' })).toBe('social');
    expect(resolveSuzentStage({ toolName: 'create_tasks' })).toBe('tasks');
  });

  it('renders constellation_command orbital satellites with front/back depth occlusion for subagent', () => {
    const pose = evaluateFullBodyAct('constellation_command', 0.8, 0, { x: 0, y: 0, rot: 0 });
    expect(pose.backHtml).toContain(`A 144`);
    expect(pose.frontHtml).toContain(`A 144`);
    expect(pose.backHtml + pose.frontHtml).toContain('<circle');
  });

  it('provides the curated multi-act rotation pools with reading (R1), ingesting (R3), starting (workout), bash (laptop_type), and writing (fountain_pen)', () => {
    expect(STAGE_SPECS.reading.acts).toEqual(['speed_reader']);
    expect(STAGE_SPECS.ingesting.acts).toEqual(['chomp_file']);
    expect(STAGE_SPECS.thinking.acts).toEqual(['thought_cloud', 'full_gear', 'eureka_levitate']);
    expect(STAGE_SPECS.searching.acts).toEqual(['big_loupe', 'peek_radar']);
    expect(STAGE_SPECS.writing.acts).toEqual(['fountain_pen']);
    expect(STAGE_SPECS.starting.acts).toEqual(['workout']);
    expect(STAGE_SPECS.bash.acts).toEqual(['laptop_type', 'dj_groove']);
    expect(STAGE_SPECS.bash.humming).toBe(false);
    expect(STAGE_SPECS.subagent.acts).toEqual([
      'constellation_command',
      'agent_twin_split',
      'agent_portal_spawn',
    ]);
    expect(STAGE_SPECS.subagent.humming).toBe(false);

    const twinPinch = evaluateFullBodyAct('agent_twin_split', 0.35, 0, { x: 0, y: 0, rot: 0 });
    expect(twinPinch.targetRing).toHaveLength(96);
    expect(twinPinch.ringBlend).toBeGreaterThan(0.5);

    const twin = evaluateFullBodyAct('agent_twin_split', 1.1, 0, { x: 0, y: 0, rot: 0 });
    expect(twin.x).toBeLessThan(-70);
    expect(twin.frontHtml).toContain('translate(192.');

    const workout = evaluateFullBodyAct('workout', 0.9, 0, { x: 0, y: 0, rot: 0 });
    expect(workout.frontHtml).toContain(`Q${HEAD_C}`);
    const openBook = evaluateFullBodyAct('speed_reader', 1.15, 0, { x: 0, y: 0, rot: 0 });
    expect(openBook.frontHtml).toContain('stroke="var(--fg)"');
    const chompFile = evaluateFullBodyAct('chomp_file', 0.45, 0, { x: 0, y: 0, rot: 0 });
    expect(chompFile.frontHtml).toContain('stroke="var(--fg)"');
    const fullGear = evaluateFullBodyAct('full_gear', 1.2, 0, { x: 0, y: 0, rot: 0 });
    expect(fullGear.targetRing).toHaveLength(96);
    expect(fullGear.ringBlend).toBe(1);
    expect(fullGear.hideEyes).toBe(true);
    expect(fullGear.backHtml).toContain('rotate(');
    const loupe = evaluateFullBodyAct('big_loupe', 0.5, 0, { x: 0, y: 0, rot: 0 });
    expect(loupe.frontHtml).toContain('<circle');
  });

  it('mounts SuzentBotMark inside ActivityRail when showSuzentBot is enabled on a live rail', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <ActivityRail
          itemCount={2}
          isCurrent
          showSuzentBot
          currentLabel="Editing main.ts"
          summaryTools={[{ toolName: 'edit_file', running: true }]}
        >
          <div>step</div>
        </ActivityRail>
      </I18nProvider>
    );
    expect(html).toContain('data-suzent-bot=""');
    expect(html).toContain('data-stage="writing"');
  });

  it('renders SuzentBotMark directly with constant viewBox="-46 -46 320.54 320.54" and does not hardcode inline --bg/#ffffff', () => {
    const html = renderToStaticMarkup(<SuzentBotMark stage="subagent" size={28} />);
    expect(html).toContain('viewBox="-46 -46 320.54 320.54"');
    expect(html).toContain('data-stage="subagent"');
    expect(html).not.toContain('--bg:#ffffff');
  });

  it('preserves the 320x108 assembly animation while thinking, keeps SuzentBotMark in the collapsed ActivityRail while tools run, and moves it to the message footer during final prose streaming and after completion', () => {
    const thinkingHtml = renderToStaticMarkup(
      <I18nProvider>
        <AssistantMessage
          message={{ role: 'assistant', content: '' }}
          messageIndex={0}
          isStreaming={true}
          isLastMessage={true}
          aguiParts={[]}
        />
      </I18nProvider>
    );
    expect(thinkingHtml).toContain('w-[320px]');
    expect(thinkingHtml).toContain('h-[108px]');
    expect(thinkingHtml).toContain('<canvas');

    const railHtml = renderToStaticMarkup(
      <I18nProvider>
        <AssistantMessage
          message={{ role: 'assistant', content: '' }}
          messageIndex={0}
          isStreaming={true}
          isLastMessage={true}
          aguiParts={[
            {
              type: 'tool',
              toolCallId: 'tc-1',
              toolName: 'grep_search',
              args: '{"pattern":"foo"}',
            },
          ]}
        />
      </I18nProvider>
    );
    expect(railHtml).toContain('activity-rail-header');
    expect(railHtml).toContain('data-suzent-bot=""');
    expect(railHtml).toContain('data-stage="searching"');

    const streamingProseHtml = renderToStaticMarkup(
      <I18nProvider>
        <AssistantMessage
          message={{ role: 'assistant', content: 'Streaming long answer...' }}
          messageIndex={0}
          isStreaming={true}
          isLastMessage={true}
          aguiParts={[
            {
              type: 'tool',
              toolCallId: 'tc-1',
              toolName: 'grep_search',
              args: '{"pattern":"foo"}',
              output: 'match',
              state: 'completed',
            },
            { type: 'text', text: 'Streaming long answer...' },
          ]}
        />
      </I18nProvider>
    );
    expect(streamingProseHtml.match(/data-suzent-bot=""/g)).toHaveLength(1);
    expect(streamingProseHtml).toContain('data-stage="writing"');

    const finishedLastHtml = renderToStaticMarkup(
      <I18nProvider>
        <AssistantMessage
          message={{ role: 'assistant', content: 'Completed long answer.' }}
          messageIndex={0}
          isStreaming={false}
          isLastMessage={true}
          aguiParts={[{ type: 'text', text: 'Completed long answer.' }]}
        />
      </I18nProvider>
    );
    expect(finishedLastHtml).toContain('data-suzent-bot=""');
    expect(finishedLastHtml).toContain('data-stage="idle"');
    const finishedWithPastFailedToolHtml = renderToStaticMarkup(
      <I18nProvider>
        <AssistantMessage
          message={{ role: 'assistant', content: 'Recovered and finished.' }}
          messageIndex={0}
          isStreaming={false}
          isLastMessage={true}
          aguiParts={[
            {
              type: 'tool',
              toolCallId: 'tc-err',
              toolName: 'run_command',
              args: '{"content":"bad"}',
              output: '[exit code: 1]',
              outcome: 'failed',
              state: 'completed',
            },
            { type: 'text', text: 'Recovered and finished.' },
          ]}
        />
      </I18nProvider>
    );
    expect(finishedWithPastFailedToolHtml).toContain('data-stage="idle"');
    expect(finishedWithPastFailedToolHtml).not.toContain('data-stage="error"');
  });

  it('steps spring physics smoothly without 2*pi stiffness overshoot', () => {
    const s = springValue(1);
    s.target = 0.05;
    // One 120Hz step at frequency=26, damping=1 should move smoothly without flipping sign
    stepSpring(s, 26, 1, 1 / 120);
    expect(s.x).toBeGreaterThan(0.5);
    expect(s.x).toBeLessThan(1);
  });

  it('renders dedicated 24x24 semantic tool-icon SVGs with internal part choreography while streaming without output, and static Heroicons once completed', () => {
    const runningRead = renderToStaticMarkup(
      <ToolGroupIcon toolName="read_file" isStreaming={true} hasOutput={false} />
    );
    expect(runningRead).toContain('data-tool-svg="read"');
    expect(runningRead).toContain('tg-read-dot');
    expect(runningRead).toContain('tool-icon-anim-scan');

    const runningEdit = renderToStaticMarkup(
      <ToolGroupIcon toolName="edit_file" isStreaming={true} hasOutput={false} />
    );
    expect(runningEdit).toContain('data-tool-svg="write"');
    expect(runningEdit).toContain('tg-write-pen');

    const runningSearch = renderToStaticMarkup(
      <ToolGroupIcon toolName="grep_search" isStreaming={true} hasOutput={false} />
    );
    expect(runningSearch).toContain('data-tool-svg="search"');
    expect(runningSearch).toContain('tg-search-glass');

    const runningBash = renderToStaticMarkup(
      <ToolGroupIcon toolName="run_command" isStreaming={true} hasOutput={false} />
    );
    expect(runningBash).toContain('data-tool-svg="terminal"');
    expect(runningBash).toContain('tg-term-cursor');

    const completedRead = renderToStaticMarkup(
      <ToolGroupIcon toolName="read_file" isStreaming={false} hasOutput={true} />
    );
    expect(completedRead).not.toContain('data-tool-svg');
    expect(completedRead).toContain('data-anim="none"');
  });
});
