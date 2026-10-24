import React from 'react';
import { renderToStaticMarkup as renderMarkup } from 'react-dom/server';
import { I18nProvider } from '../../i18n';
import { beforeAll, afterAll, describe, expect, it, vi } from 'vitest';
import {
  ActivityRail,
  WorkedDuration,
  ActivityRailItem,
  TurnActivity,
  getFinalContentStart,
} from './ActivityRail';

beforeAll(() => vi.stubGlobal('navigator', { language: 'en', languages: ['en'] }));
afterAll(() => vi.unstubAllGlobals());

function renderToStaticMarkup(node: React.ReactNode): string {
  return renderMarkup(<I18nProvider>{node}</I18nProvider>);
}

function renderRail(props: Partial<React.ComponentProps<typeof ActivityRail>>): string {
  return renderToStaticMarkup(
    <ActivityRail itemCount={5} {...props}>
      {props.children ?? <div />}
    </ActivityRail>
  );
}

it('shows thinking animation instead of the previous tool in a collapsed rail', () => {
  const props = {
    isCurrent: true,
    isThinking: true,
    currentLabel: 'Thinking: Reviewing the result',
    summaryTools: [{ toolName: 'read_file', running: false }],
  };
  const markup = renderRail(props);
  expect(markup).not.toContain('robot-streaming');
  expect(markup).toContain('reasoning-thinking-label');
  expect(markup).not.toContain('tool-group-icon');
  expect(renderRail({ ...props, isCurrent: false })).not.toContain('reasoning-thinking-label');
  expect(renderRail({ ...props, defaultExpanded: true })).not.toContain('reasoning-thinking-label');
});

it('keeps the delegated agent avatar animated after the spawn call returns', () => {
  const renderAgent = (status: string): string =>
    renderRail({
      isCurrent: true,
      currentLabel: 'Delegated task',
      summaryTools: [
        {
          toolName: 'agent',
          running: false,
          output: JSON.stringify({ metadata: { task_id: 'sub_test', status } }),
        },
      ],
    });
  expect(renderAgent('running')).toContain('animate-pulse');
  expect(renderAgent('running')).toContain('activity-turn-tool');
  expect(renderAgent('queued')).toContain('animate-pulse');
  expect(renderAgent('completed')).not.toContain('animate-pulse');
  expect(renderAgent('failed')).not.toContain('activity-turn-tool');
});

// A turn that interleaves prose with tool calls renders one rail per activity
// group. Every rail used to claim the turn's worked-for time and to animate as
// if it were live, so a long turn showed several identical running headers.
describe('ActivityRail header', () => {
  it('reports the worked time on the first rail of a turn only', () => {
    expect(renderToStaticMarkup(<WorkedDuration durationSeconds={65} />)).toContain(
      'Worked for 1m 5s'
    );
    expect(renderRail({ isActive: true })).not.toContain('Worked for');
  });

  it('describes its own work instead of repeating the duration', () => {
    const markup = renderRail({
      isActive: true,
      isCurrent: false,
      currentLabel: 'Read main.py',
    });

    expect(markup).toContain('Read main.py');
    expect(markup).not.toContain('Worked for');
  });

  it('animates only the rail the agent is working in', () => {
    const settled = renderRail({
      isActive: true,
      isCurrent: false,
      currentLabel: 'Ran 4 commands',
    });
    const live = renderRail({
      isActive: true,
      isCurrent: true,
      currentLabel: 'Running npm test',
    });

    expect(settled).not.toContain('activity-rail-header-active');
    expect(live).toContain('activity-rail-header-active');
  });

  it('falls back to a neutral label when the group exposes nothing to describe', () => {
    expect(renderRail({ isActive: true, isCurrent: false })).toContain('Activity');
  });
});

it('renders repeated calls directly without another disclosure', () => {
  const markup = renderToStaticMarkup(
    <ActivityRail itemCount={2} defaultExpanded>
      <ActivityRailItem toolName="read_file" state="done">
        old details
      </ActivityRailItem>
      <ActivityRailItem toolName="read_file" state="active">
        latest details
      </ActivityRailItem>
    </ActivityRail>
  );
  expect(markup).toContain('latest details');
  expect(markup).not.toContain('×2');
  expect(markup).toContain('old details');
  expect(markup.match(/aria-expanded=/g)).toHaveLength(1);
});
it('keeps approvals outside repeated groups', () => {
  const markup = renderToStaticMarkup(
    <ActivityRail itemCount={2} defaultExpanded>
      <ActivityRailItem toolName="read_file" state="done">
        old details
      </ActivityRailItem>
      <ActivityRailItem toolName="read_file" state="pending">
        approve this call
      </ActivityRailItem>
    </ActivityRail>
  );
  expect(markup).not.toContain('×2');
  expect(markup).toContain('approve this call');
});

describe('TurnActivity', () => {
  const children = [
    <div key="work">intermediate commentary</div>,
    <div key="tool">tool details</div>,
    <div key="final">final answer</div>,
  ];
  it('collapses all work under the duration and leaves the final answer visible', () => {
    const markup = renderToStaticMarkup(
      <TurnActivity finalStart={2} isStreaming={false} durationSeconds={68}>
        {children}
      </TurnActivity>
    );
    expect(markup).toContain('Worked for 1m 8s');
    expect(markup).toContain('final answer');
    expect(markup).not.toContain('intermediate commentary');
    expect(markup).not.toContain('tool details');
  });
  it('opens the tool list directly during streaming, without an outer disclosure', () => {
    const markup = renderToStaticMarkup(
      <TurnActivity finalStart={1} isStreaming>
        {[
          <ActivityRail key="tools" itemCount={2} isCurrent currentLabel="Running npm test">
            <ActivityRailItem>tool details</ActivityRailItem>
          </ActivityRail>,
        ]}
      </TurnActivity>
    );
    expect(markup).toContain('Worked for');
    expect(markup).toContain('Running npm test');
    expect(markup).toContain('activity-rail-header-active');
    expect(markup.match(/aria-expanded=/g)).toHaveLength(1);
    expect(markup).not.toContain('tool details');
  });
  it('exposes approval controls and flattens rails without nested group disclosures', () => {
    const markup = renderToStaticMarkup(
      <TurnActivity finalStart={1} isStreaming>
        {[
          <ActivityRail key="tools" itemCount={2} defaultExpanded>
            <ActivityRailItem toolName="read_file">first call</ActivityRailItem>
            <ActivityRailItem toolName="read_file" state="pending">
              approval controls
            </ActivityRailItem>
          </ActivityRail>,
        ]}
      </TurnActivity>
    );
    expect(markup).toContain('first call');
    expect(markup).toContain('approval controls');
    expect(markup.match(/aria-expanded=/g)).toHaveLength(1);
  });
  it('keeps only trailing answer content outside the work disclosure', () => {
    expect(
      getFinalContentStart([
        { type: 'single', chunk: { type: 'text' }, index: 0 },
        { type: 'activity', chunks: [] },
        { type: 'single', chunk: { type: 'text' }, index: 2 },
      ])
    ).toBe(2);
    expect(getFinalContentStart([{ type: 'activity', chunks: [] }])).toBe(1);
    expect(getFinalContentStart([{ type: 'single', chunk: { type: 'content' }, index: 0 }])).toBe(
      0
    );
  });
});

it('shows the running timer before any tool activity', () => {
  const now = Date.now();
  vi.spyOn(Date, 'now').mockReturnValue(now);
  try {
    const markup = renderToStaticMarkup(
      <TurnActivity finalStart={0} isStreaming startedAtMs={now - 3000} durationSeconds={1}>
        {[<div key="text">streaming prose</div>]}
      </TurnActivity>
    );
    expect(markup).toContain('Worked for 3s');
    expect(markup).toContain('streaming prose');
    expect(markup).not.toContain('aria-expanded');
  } finally {
    vi.restoreAllMocks();
  }
});

it('collapses separate rails when commentary appears inside the work history', () => {
  const markup = renderRail({
    currentLabel: 'Read source files',
    children: <div>tool history</div>,
  });
  expect(markup).toContain('Read source files');
  expect(markup).toContain('aria-expanded="false"');
  expect(markup).not.toContain('tool history');
});

it('keeps pending approval visible even when the rail defaults to collapsed', () => {
  const markup = renderRail({ hasPending: true, children: <button>Approve tool</button> });
  expect(markup).toContain('aria-expanded="true"');
  expect(markup).toContain('Approve tool');
});
it('avoids a redundant step count beside the work summary and exposes the full label', () => {
  const markup = renderRail({ summaryTools: [{ toolName: 'run_command' }] });
  expect(markup).toContain('title="Commands run: 1"');
  expect(markup).not.toContain('5 steps');
});

it('limits scrolling to the inner rail', () => {
  const markup = renderToStaticMarkup(
    <TurnActivity finalStart={1} isStreaming>
      {[
        <ActivityRail key="rail" itemCount={1} defaultExpanded>
          <ActivityRailItem>tool content</ActivityRailItem>
        </ActivityRail>,
      ]}
    </TurnActivity>
  );
  expect(markup.match(/overflow-y-auto/g)).toHaveLength(1);
  expect(markup.match(/max-h-\[min\(24rem,50vh\)\]/g)).toHaveLength(1);
  expect(markup).toContain('tool content');
});

// The capped rail sits on top of the transcript. Containing its overscroll
// stops the wheel dead once the rail reaches its own top or bottom, so the chat
// behind it cannot be scrolled while the pointer is over an expanded rail.
it('lets scrolling chain to the chat once the rail reaches its edge', () => {
  const markup = renderRail({ defaultExpanded: true, children: <div>tool content</div> });
  expect(markup).toContain('activity-rail-scroll');
  expect(markup).not.toContain('overscroll-contain');
  expect(markup).not.toContain('overscroll-none');
});

it('keeps a tool-only rail summary collapsed inside the expanded turn', () => {
  const markup = renderToStaticMarkup(
    <TurnActivity finalStart={1} isStreaming>
      {[
        <ActivityRail
          key="tools"
          itemCount={2}
          summaryTools={[{ toolName: 'run_command' }, { toolName: 'run_command' }]}
        >
          <ActivityRailItem>first command details</ActivityRailItem>
          <ActivityRailItem>second command details</ActivityRailItem>
        </ActivityRail>,
      ]}
    </TurnActivity>
  );
  expect(markup).toContain('Commands run: 2');
  expect(markup).toContain('aria-expanded="false"');
  expect(markup).not.toContain('first command details');
});

it('associates collapsed controls with hidden bodies', () => {
  const markup = renderRail({ currentLabel: 'Tool history' });
  const controlledId = markup.match(/aria-controls="([^"]+)"/)?.[1];
  expect(controlledId).toBeTruthy();
  expect(markup).toContain(`id="${controlledId}"`);
  expect(markup).toContain('aria-hidden="true"');
  expect(markup).toContain('visibility:hidden');
});

it('uses a group summary rather than repeating the live tool name', () => {
  const markup = renderRail({
    isCurrent: true,
    defaultExpanded: true,
    currentLabel: 'Checked agent sub_123',
    summaryTools: [{ toolName: 'run_command' }, { toolName: 'agent_check', running: true }],
  });
  expect(markup).toContain('Commands run: 1 · In progress: 1');
  expect(markup).not.toContain('Checked agent sub_123');
});

it('preserves the specific tool animation while the rail is collapsed', () => {
  const props = {
    isCurrent: true,
    currentLabel: 'Editing main.ts',
    summaryTools: [{ toolName: 'edit_file', running: true }],
  };
  const collapsed = renderRail(props);
  expect(collapsed).toContain('brutal-running-dots');
  expect(collapsed).toContain('Editing main.ts');
  expect(renderRail({ ...props, defaultExpanded: true })).not.toContain('brutal-running-dots');
  expect(renderRail({ ...props, isCurrent: false })).not.toContain('brutal-running-dots');
});

it('keeps the memory icon after completion without suggesting the call is still running', () => {
  const completed = renderRail({
    isCurrent: true,
    currentLabel: 'Searched memory',
    summaryTools: [{ toolName: 'memory_search', running: false }],
  });
  expect(completed.match(/<svg/g)).toHaveLength(2);
  expect(completed).not.toContain('activity-rail-header-active');
  expect(completed).not.toContain('tool-icon-anim-');
  const running = renderRail({
    isCurrent: true,
    currentLabel: 'Searching memory',
    summaryTools: [{ toolName: 'memory_search', running: true }],
  });
  expect(running).toContain('tool-icon-anim-memory');
});
