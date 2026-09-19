import React, { useEffect, useMemo, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import type { ScheduleKind } from '../../lib/api';
import { BrutalSelect } from '../BrutalSelect';
import { BrutalMultiSelect } from '../BrutalMultiSelect';

/**
 * Friendly schedule picker for every kind of scheduled task.
 *
 * Most users never have to know what cron is: they pick a frequency and the
 * builder emits whichever shape the backend needs — a cron expression, a fixed
 * interval, or a single timestamp. A raw-cron escape hatch remains for power
 * users and for expressions the picker can't represent.
 */

/** Everything that decides *when* a task fires. Binding (where it runs) is separate. */
export interface ScheduleValue {
  schedule_kind: ScheduleKind;
  cron_expr: string;
  interval_minutes: number | null;
  run_at: string | null;
  timezone: string | null;
  jitter_seconds: number;
  catch_up: 'skip' | 'run_once';
}

export const DEFAULT_SCHEDULE: ScheduleValue = {
  schedule_kind: 'cron',
  cron_expr: '0 9 * * *',
  interval_minutes: null,
  run_at: null,
  timezone: null,
  jitter_seconds: 0,
  catch_up: 'skip',
};

type Frequency = 'interval' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'once' | 'advanced';

/** Frequencies that repeat, and so can meaningfully jitter or miss a run. */
const REPEATING: Frequency[] = ['interval', 'hourly', 'daily', 'weekly', 'monthly', 'advanced'];

interface ScheduleBuilderProps {
  value: ScheduleValue;
  onChange: (value: ScheduleValue) => void;
}

const WEEKDAYS = ['0', '1', '2', '3', '4', '5', '6']; // Sun..Sat (cron dow)

interface Parsed {
  frequency: Frequency;
  interval: number; // for "every N minutes"
  hour: number;
  minute: number;
  weekdays: string[]; // cron dow values, e.g. ["1","3","5"]
  dayOfMonth: number;
}

const DEFAULTS: Parsed = {
  frequency: 'daily',
  interval: 15,
  hour: 9,
  minute: 0,
  weekdays: ['1'],
  dayOfMonth: 1,
};

const WEEKDAYS_PRESET = ['1', '2', '3', '4', '5']; // Mon–Fri
const EVERYDAY_PRESET = ['0', '1', '2', '3', '4', '5', '6'];

/** Expand a cron day-of-week field ("1", "1-5", "1,3,5") into sorted values. */
function expandDow(field: string): string[] {
  const out = new Set<string>();
  for (const part of field.split(',')) {
    const range = /^(\d)-(\d)$/.exec(part.trim());
    if (range) {
      for (let i = Number(range[1]); i <= Number(range[2]); i++) out.add(String(i));
    } else if (/^\d$/.test(part.trim())) {
      out.add(part.trim());
    }
  }
  return [...out].sort();
}

/** Best-effort parse of a 5-field cron string into the friendly model. */
function parseCron(cron: string): Parsed {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return { ...DEFAULTS, frequency: cron.trim() ? 'advanced' : 'daily' };
  const [min, hr, dom, , dow] = parts;

  const num = (s: string) => {
    const n = Number(s);
    return Number.isFinite(n) ? n : NaN;
  };

  // Every N minutes: "*/N * * * *"
  const everyMin = /^\*\/(\d+)$/.exec(min);
  if (everyMin && hr === '*' && dom === '*' && dow === '*') {
    return { ...DEFAULTS, frequency: 'interval', interval: Number(everyMin[1]) };
  }
  // Hourly: "M * * * *"
  if (!isNaN(num(min)) && hr === '*' && dom === '*' && dow === '*') {
    return { ...DEFAULTS, frequency: 'hourly', minute: num(min) };
  }
  // Daily: "M H * * *"
  if (!isNaN(num(min)) && !isNaN(num(hr)) && dom === '*' && dow === '*') {
    return { ...DEFAULTS, frequency: 'daily', minute: num(min), hour: num(hr) };
  }
  // Weekly: "M H * * D" where D is a day, list (1,3,5), or range (1-5).
  if (!isNaN(num(min)) && !isNaN(num(hr)) && dom === '*' && dow !== '*') {
    const days = expandDow(dow);
    if (days.length > 0) {
      return { ...DEFAULTS, frequency: 'weekly', minute: num(min), hour: num(hr), weekdays: days };
    }
  }
  // Monthly: "M H D * *"
  if (!isNaN(num(min)) && !isNaN(num(hr)) && !isNaN(num(dom)) && dow === '*') {
    return {
      ...DEFAULTS,
      frequency: 'monthly',
      minute: num(min),
      hour: num(hr),
      dayOfMonth: num(dom),
    };
  }
  return { ...DEFAULTS, frequency: 'advanced' };
}

/** Build a cron string from the friendly model. */
function buildCron(p: Parsed): string {
  switch (p.frequency) {
    case 'hourly':
      return `${p.minute} * * * *`;
    case 'daily':
      return `${p.minute} ${p.hour} * * *`;
    case 'weekly': {
      const days = (p.weekdays.length ? p.weekdays : ['1']).slice().sort();
      return `${p.minute} ${p.hour} * * ${days.join(',')}`;
    }
    case 'monthly':
      return `${p.minute} ${p.hour} ${p.dayOfMonth} * *`;
    default:
      return '';
  }
}

/** Format a Date for a `datetime-local` input: local wall time, no zone. */
function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

type Translate = (key: string, vars?: Record<string, string>) => string;

/** One-line summary of a task's schedule, whatever kind it is.
 *
 * Only cron tasks have an expression to parse; an interval or one-shot task
 * would otherwise render as a blank where its schedule should be.
 */
export function describeSchedule(
  job: {
    schedule_kind?: string;
    cron_expr: string;
    interval_minutes?: number | null;
    run_at?: string | null;
    timezone?: string | null;
  },
  t: Translate
): string {
  switch (job.schedule_kind) {
    case 'interval':
      return t('settings.automation.summaryMinutes', { n: String(job.interval_minutes ?? '?') });
    case 'once':
      return job.run_at
        ? t('settings.automation.summaryOnce', { time: new Date(job.run_at).toLocaleString() })
        : t('settings.automation.summaryOnceUnset');
    default: {
      const base = describeCron(job.cron_expr, t);
      return job.timezone ? `${base} (${job.timezone})` : base;
    }
  }
}

/** Plain-language summary of a cron string, or the raw cron if it doesn't map to
 *  a known pattern. Driven by the i18n `t` function so it is fully localizable. */
export function describeCron(cron: string, t: Translate): string {
  const p = parseCron(cron);
  const time = `${String(p.hour).padStart(2, '0')}:${String(p.minute).padStart(2, '0')}`;
  const weekdayLabels = t('settings.automation.weekdays').split(',');
  switch (p.frequency) {
    case 'interval':
      return t('settings.automation.summaryMinutes', { n: String(p.interval) });
    case 'hourly':
      return t('settings.automation.summaryHourly', { m: String(p.minute).padStart(2, '0') });
    case 'daily':
      return t('settings.automation.summaryDaily', { time });
    case 'weekly': {
      const days = p.weekdays.slice().sort();
      const key = days.join(',');
      let dayText: string;
      if (key === WEEKDAYS_PRESET.join(',')) dayText = t('settings.automation.weekdaysShort');
      else if (key === EVERYDAY_PRESET.join(',')) dayText = t('settings.automation.everyDayShort');
      else dayText = days.map((d) => weekdayLabels[Number(d)] ?? d).join(', ');
      return t('settings.automation.summaryWeekly', { day: dayText, time });
    }
    case 'monthly':
      return t('settings.automation.summaryMonthly', { day: String(p.dayOfMonth), time });
    default:
      return cron;
  }
}

/** Every control in the builder, in one object so a change emits atomically. */
interface BuilderState extends Parsed {
  runAt: string; // datetime-local text
  advancedCron: string;
  timezone: string; // '' means follow the machine
  jitter: number;
  catchUp: 'skip' | 'run_once';
}

function fromValue(value: ScheduleValue): BuilderState {
  const parsed = parseCron(value.cron_expr);
  const common = {
    runAt: value.run_at
      ? toLocalInput(new Date(value.run_at))
      : toLocalInput(new Date(Date.now() + 60 * 60 * 1000)),
    advancedCron: value.cron_expr,
    timezone: value.timezone || '',
    jitter: value.jitter_seconds || 0,
    catchUp: value.catch_up || 'skip',
  };

  if (value.schedule_kind === 'interval') {
    return {
      ...DEFAULTS,
      ...common,
      frequency: 'interval',
      interval: value.interval_minutes || DEFAULTS.interval,
    };
  }
  if (value.schedule_kind === 'once') {
    return { ...DEFAULTS, ...common, frequency: 'once' };
  }
  return { ...parsed, ...common };
}

function toValue(s: BuilderState): ScheduleValue {
  const policy = {
    timezone: s.timezone || null,
    jitter_seconds: s.frequency === 'once' ? 0 : s.jitter,
    catch_up: s.catchUp,
  };

  if (s.frequency === 'interval') {
    return {
      ...policy,
      schedule_kind: 'interval',
      cron_expr: '',
      interval_minutes: Math.max(1, s.interval),
      run_at: null,
    };
  }
  if (s.frequency === 'once') {
    return {
      ...policy,
      schedule_kind: 'once',
      cron_expr: '',
      interval_minutes: null,
      run_at: s.runAt || null,
    };
  }
  return {
    ...policy,
    schedule_kind: 'cron',
    cron_expr: s.frequency === 'advanced' ? s.advancedCron : buildCron(s),
    interval_minutes: null,
    run_at: null,
  };
}

/** A schedule as the builder would re-emit it after loading it.
 *
 * The edit form round-trips through the builder's controls, so anything this
 * loses would be silently lost the moment a user touched an unrelated field.
 */
export function normalizeSchedule(value: ScheduleValue): ScheduleValue {
  return toValue(fromValue(value));
}

/** Stable text form of a schedule, for comparing two of them.
 *
 * Key order has to be fixed: callers build these objects field by field, and a
 * plain JSON.stringify would call two identical schedules different purely
 * because their keys were written in a different order.
 */
export function serializeSchedule(v: ScheduleValue): string {
  return JSON.stringify([
    v.schedule_kind,
    v.cron_expr,
    v.interval_minutes,
    v.run_at,
    v.timezone,
    v.jitter_seconds,
    v.catch_up,
  ]);
}

/** Timezones the browser knows about, or a short fallback list for older ones. */
function timezoneNames(): string[] {
  const supported = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] })
    .supportedValuesOf;
  if (typeof supported === 'function') {
    try {
      return supported('timeZone');
    } catch {
      /* fall through to the short list */
    }
  }
  return [
    'UTC',
    'Asia/Shanghai',
    'Asia/Tokyo',
    'Asia/Singapore',
    'Europe/London',
    'Europe/Berlin',
    'America/New_York',
    'America/Los_Angeles',
  ];
}

export function ScheduleBuilder({ value, onChange }: ScheduleBuilderProps): React.ReactElement {
  const { t } = useI18n();
  const [state, setState] = useState<BuilderState>(() => fromValue(value));

  // Re-seed only when the *parent* changes the value (e.g. opening the edit
  // form), never when we are the ones who just emitted it — otherwise every
  // keystroke would round-trip and clobber the control being edited.
  const serialized = serializeSchedule(value);
  const lastEmitted = useRef(serialized);
  const incoming = useRef(value);
  incoming.current = value;
  useEffect(() => {
    if (serialized === lastEmitted.current) return;
    lastEmitted.current = serialized;
    setState(fromValue(incoming.current));
  }, [serialized]);

  const update = (patch: Partial<BuilderState>) => {
    const next = { ...state, ...patch };
    setState(next);
    const emitted = toValue(next);
    lastEmitted.current = serializeSchedule(emitted);
    onChange(emitted);
  };

  const fieldLabel = (text: string) => (
    <label className="block font-bold tracking-wide text-brutal-black dark:text-white uppercase mb-1 text-xs">
      {text}
    </label>
  );

  // Keep schedule fields crisp without adding another heavy shadow layer.
  const brutalInput =
    'bg-white dark:bg-zinc-800 dark:text-white border-2 border-brutal-black px-3 py-2 font-bold text-sm focus:outline-none';

  const numberInput = (
    val: number,
    min: number,
    max: number | undefined,
    onVal: (n: number) => void
  ) => (
    <input
      type="number"
      min={min}
      {...(max !== undefined ? { max } : {})}
      value={val}
      onChange={(e) => {
        let n = Number(e.target.value) || min;
        n = Math.max(min, max !== undefined ? Math.min(max, n) : n);
        onVal(n);
      }}
      className={`w-24 ${brutalInput}`}
    />
  );

  const timeInput = (
    <input
      type="time"
      value={`${String(state.hour).padStart(2, '0')}:${String(state.minute).padStart(2, '0')}`}
      onChange={(e) => {
        const [h, m] = e.target.value.split(':').map(Number);
        update({ hour: h || 0, minute: m || 0 });
      }}
      className={brutalInput}
    />
  );

  const frequencyOptions = useMemo(
    () => [
      { value: 'interval', label: t('settings.automation.freqMinutes') },
      { value: 'hourly', label: t('settings.automation.freqHourly') },
      { value: 'daily', label: t('settings.automation.freqDaily') },
      { value: 'weekly', label: t('settings.automation.freqWeekly') },
      { value: 'monthly', label: t('settings.automation.freqMonthly') },
      { value: 'once', label: t('settings.automation.freqOnce') },
      { value: 'advanced', label: t('settings.automation.freqAdvanced') },
    ],
    [t]
  );

  const weekdayOptions = useMemo(() => {
    const labels = t('settings.automation.weekdays').split(',');
    return WEEKDAYS.map((d, i) => ({ value: d, label: labels[i] ?? d }));
  }, [t]);

  const timezoneOptions = useMemo(
    () => [
      { value: '', label: t('settings.automation.tzLocal') },
      ...timezoneNames().map((tz) => ({ value: tz, label: tz })),
    ],
    [t]
  );

  const catchUpOptions = useMemo(
    () => [
      { value: 'skip', label: t('settings.automation.catchUpSkip') },
      { value: 'run_once', label: t('settings.automation.catchUpRunOnce') },
    ],
    [t]
  );

  const isCron = state.frequency !== 'interval' && state.frequency !== 'once';
  const repeats = REPEATING.includes(state.frequency);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-3 items-end">
        <BrutalSelect
          value={state.frequency}
          onChange={(val) => {
            const frequency = val as Frequency;
            if (frequency === 'advanced') {
              // Seed the raw box with the current built cron so nothing is lost.
              update({ frequency, advancedCron: state.advancedCron || buildCron(state) });
            } else {
              update({ frequency });
            }
          }}
          options={frequencyOptions}
          label={t('settings.automation.repeat')}
          className="w-44"
        />

        {state.frequency === 'interval' && (
          <div>
            {fieldLabel(t('settings.automation.intervalLabel'))}
            {numberInput(state.interval, 1, undefined, (n) => update({ interval: n }))}
          </div>
        )}

        {state.frequency === 'once' && (
          <div>
            {fieldLabel(t('settings.automation.runAtLabel'))}
            <input
              type="datetime-local"
              value={state.runAt}
              onChange={(e) => update({ runAt: e.target.value })}
              className={brutalInput}
            />
          </div>
        )}

        {state.frequency === 'hourly' && (
          <div>
            {fieldLabel(t('settings.automation.atMinuteLabel'))}
            {numberInput(state.minute, 0, 59, (n) => update({ minute: n }))}
          </div>
        )}

        {state.frequency === 'weekly' && (
          <div className="flex items-end gap-2 flex-wrap">
            <BrutalMultiSelect
              value={state.weekdays}
              onChange={(days) => update({ weekdays: days.length ? days : state.weekdays })}
              options={weekdayOptions}
              label={t('settings.automation.onDaysLabel')}
              className="w-56"
            />
            <div className="flex gap-1 pb-0.5">
              <button
                type="button"
                onClick={() => update({ weekdays: WEEKDAYS_PRESET })}
                className="px-2 py-1 text-[10px] font-bold uppercase border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white hover:bg-brutal-yellow dark:hover:bg-zinc-600 transition-colors"
              >
                {t('settings.automation.weekdaysShort')}
              </button>
              <button
                type="button"
                onClick={() => update({ weekdays: EVERYDAY_PRESET })}
                className="px-2 py-1 text-[10px] font-bold uppercase border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white hover:bg-brutal-yellow dark:hover:bg-zinc-600 transition-colors"
              >
                {t('settings.automation.everyDayShort')}
              </button>
            </div>
          </div>
        )}

        {state.frequency === 'monthly' && (
          <div>
            {fieldLabel(t('settings.automation.onDayOfMonthLabel'))}
            {numberInput(state.dayOfMonth, 1, 31, (n) => update({ dayOfMonth: n }))}
          </div>
        )}

        {(state.frequency === 'daily' ||
          state.frequency === 'weekly' ||
          state.frequency === 'monthly') && (
          <div>
            {fieldLabel(t('settings.automation.atTimeLabel'))}
            {timeInput}
          </div>
        )}
      </div>

      {state.frequency === 'advanced' && (
        <div className="space-y-1">
          <input
            value={state.advancedCron}
            onChange={(e) => update({ advancedCron: e.target.value })}
            placeholder={t('settings.automation.cronExprPlaceholder')}
            className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500"
          />
          <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
            {t('settings.automation.advancedHint')}
          </p>
        </div>
      )}

      {/* Timing policy: only meaningful for a schedule that recurs. */}
      {repeats && (
        <div className="flex flex-wrap gap-3 items-end pt-1">
          {isCron && (
            <BrutalSelect
              value={state.timezone}
              onChange={(tz) => update({ timezone: tz })}
              options={timezoneOptions}
              label={t('settings.automation.timezone')}
              className="w-56"
            />
          )}
          <div>
            {fieldLabel(t('settings.automation.jitterLabel'))}
            {numberInput(state.jitter, 0, 3600, (n) => update({ jitter: n }))}
          </div>
          <BrutalSelect
            value={state.catchUp}
            onChange={(val) => update({ catchUp: val as 'skip' | 'run_once' })}
            options={catchUpOptions}
            label={t('settings.automation.catchUp')}
            className="w-52"
          />
        </div>
      )}

      {state.frequency !== 'advanced' && (
        <p className="text-xs text-neutral-600 dark:text-neutral-300">
          {describeSchedule(toValue(state), t)}
        </p>
      )}
    </div>
  );
}
