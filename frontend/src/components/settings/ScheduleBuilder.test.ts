import { describe, expect, it } from 'vitest';

import {
  DEFAULT_SCHEDULE,
  type ScheduleValue,
  describeSchedule,
  normalizeSchedule,
  serializeSchedule,
} from './ScheduleBuilder';

const t = (key: string, vars?: Record<string, string>) =>
  `${key}${vars ? `:${Object.values(vars).join('|')}` : ''}`;

const schedule = (patch: Partial<ScheduleValue>): ScheduleValue => ({
  ...DEFAULT_SCHEDULE,
  ...patch,
});

describe('normalizeSchedule', () => {
  // Loading a task into the edit form and touching any control re-emits the
  // whole schedule, so a lossy round-trip would corrupt tasks on unrelated edits.
  it.each([
    ['daily cron', schedule({ cron_expr: '30 7 * * *' })],
    ['weekday cron', schedule({ cron_expr: '0 9 * * 1,2,3,4,5' })],
    ['monthly cron', schedule({ cron_expr: '0 0 15 * *' })],
    ['hourly cron', schedule({ cron_expr: '20 * * * *' })],
    [
      'cron with a timezone and jitter',
      schedule({ cron_expr: '0 9 * * *', timezone: 'Asia/Shanghai', jitter_seconds: 120 }),
    ],
    [
      'interval',
      schedule({
        schedule_kind: 'interval',
        cron_expr: '',
        interval_minutes: 45,
        catch_up: 'run_once',
      }),
    ],
  ])('preserves a %s', (_label, value) => {
    expect(normalizeSchedule(value)).toEqual(value);
  });

  it('keeps a one-shot on its timestamp', () => {
    const value = schedule({
      schedule_kind: 'once',
      cron_expr: '',
      run_at: '2026-03-04T08:30',
    });

    expect(normalizeSchedule(value)).toEqual(value);
  });

  it('carries an interval longer than an hour, which cron could not express', () => {
    // "*/90 * * * *" is not a valid 90-minute schedule, which is why long
    // intervals are their own kind rather than a cron expression.
    const value = schedule({ schedule_kind: 'interval', cron_expr: '', interval_minutes: 90 });

    expect(normalizeSchedule(value).interval_minutes).toBe(90);
  });

  it('reads a legacy every-N-minutes cron job as an interval', () => {
    const normalized = normalizeSchedule(schedule({ cron_expr: '*/15 * * * *' }));

    expect(normalized.schedule_kind).toBe('interval');
    expect(normalized.interval_minutes).toBe(15);
  });

  it('leaves an expression the picker cannot model exactly as it was', () => {
    const value = schedule({ cron_expr: '5 0 * * 1#2' });

    expect(normalizeSchedule(value).cron_expr).toBe('5 0 * * 1#2');
  });

  it('drops jitter from a one-shot, which has nothing to spread', () => {
    const value = schedule({
      schedule_kind: 'once',
      cron_expr: '',
      run_at: '2026-03-04T08:30',
      jitter_seconds: 300,
    });

    expect(normalizeSchedule(value).jitter_seconds).toBe(0);
  });
});

describe('serializeSchedule', () => {
  it('ignores the order the fields were written in', () => {
    const a: ScheduleValue = {
      schedule_kind: 'interval',
      cron_expr: '',
      interval_minutes: 10,
      run_at: null,
      timezone: null,
      jitter_seconds: 0,
      catch_up: 'skip',
    };
    const b: ScheduleValue = {
      catch_up: 'skip',
      jitter_seconds: 0,
      timezone: null,
      run_at: null,
      interval_minutes: 10,
      cron_expr: '',
      schedule_kind: 'interval',
    };

    expect(serializeSchedule(a)).toBe(serializeSchedule(b));
  });

  it('tells two different schedules apart', () => {
    expect(serializeSchedule(schedule({ cron_expr: '0 9 * * *' }))).not.toBe(
      serializeSchedule(schedule({ cron_expr: '0 10 * * *' }))
    );
  });
});

describe('describeSchedule', () => {
  it('describes an interval without inventing a cron expression', () => {
    expect(
      describeSchedule({ schedule_kind: 'interval', cron_expr: '', interval_minutes: 20 }, t)
    ).toBe('settings.automation.summaryMinutes:20');
  });

  it('names the timezone a cron task is pinned to', () => {
    expect(
      describeSchedule({ schedule_kind: 'cron', cron_expr: '0 9 * * *', timezone: 'Asia/Tokyo' }, t)
    ).toContain('(Asia/Tokyo)');
  });

  it('says so when a one-shot has no time yet', () => {
    expect(describeSchedule({ schedule_kind: 'once', cron_expr: '', run_at: null }, t)).toBe(
      'settings.automation.summaryOnceUnset'
    );
  });
});
