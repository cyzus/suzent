import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ActivityRail } from './ActivityRail';

function renderRail(props: Partial<React.ComponentProps<typeof ActivityRail>>): string {
  return renderToStaticMarkup(
    <ActivityRail itemCount={5} {...props}>
      <div />
    </ActivityRail>
  );
}

// A turn that interleaves prose with tool calls renders one rail per activity
// group. Every rail used to claim the turn's worked-for time and to animate as
// if it were live, so a long turn showed several identical running headers.
describe('ActivityRail header', () => {
  it('reports the worked time on the first rail of a turn only', () => {
    expect(renderRail({ showDuration: true, isActive: true, isCurrent: false })).toContain(
      'Worked for'
    );
  });

  it('describes its own work instead of repeating the duration', () => {
    const markup = renderRail({
      showDuration: false,
      isActive: true,
      isCurrent: false,
      currentLabel: 'Read main.py',
    });

    expect(markup).toContain('Read main.py');
    expect(markup).not.toContain('Worked for');
  });

  it('animates only the rail the agent is working in', () => {
    const settled = renderRail({
      showDuration: false,
      isActive: true,
      isCurrent: false,
      currentLabel: 'Ran 4 commands',
    });
    const live = renderRail({
      showDuration: false,
      isActive: true,
      isCurrent: true,
      currentLabel: 'Running npm test',
    });

    expect(settled).not.toContain('activity-rail-header-active');
    expect(live).toContain('activity-rail-header-active');
  });

  it('falls back to a neutral label when the group exposes nothing to describe', () => {
    expect(renderRail({ showDuration: false, isActive: true, isCurrent: false })).toContain(
      'Activity'
    );
  });
});
