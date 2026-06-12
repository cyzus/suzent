import React, { useEffect, useMemo, useState } from 'react';

import { useI18n } from '../../i18n';
import { BrutalSelect } from '../BrutalSelect';
import { BrutalMultiSelect } from '../BrutalMultiSelect';

/**
 * Friendly schedule picker that reads and emits a standard 5-field cron string,
 * so most users never have to know what cron is. A raw-cron escape hatch remains
 * for power users and for expressions the picker can't represent.
 */

type Frequency = 'minutes' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'advanced';

interface ScheduleBuilderProps {
    value: string; // cron expression
    onChange: (cron: string) => void;
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
        return { ...DEFAULTS, frequency: 'minutes', interval: Number(everyMin[1]) };
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
        return { ...DEFAULTS, frequency: 'monthly', minute: num(min), hour: num(hr), dayOfMonth: num(dom) };
    }
    return { ...DEFAULTS, frequency: 'advanced' };
}

/** Build a cron string from the friendly model. */
function buildCron(p: Parsed): string {
    switch (p.frequency) {
        case 'minutes':
            return `*/${Math.max(1, p.interval)} * * * *`;
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

type Translate = (key: string, vars?: Record<string, string>) => string;

/** Plain-language summary of a cron string, or the raw cron if it doesn't map to
 *  a known pattern. Driven by the i18n `t` function so it is fully localizable. */
export function describeCron(cron: string, t: Translate): string {
    const p = parseCron(cron);
    const time = `${String(p.hour).padStart(2, '0')}:${String(p.minute).padStart(2, '0')}`;
    const weekdayLabels = t('settings.automation.weekdays').split(',');
    switch (p.frequency) {
        case 'minutes':
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
            else dayText = days.map(d => weekdayLabels[Number(d)] ?? d).join(', ');
            return t('settings.automation.summaryWeekly', { day: dayText, time });
        }
        case 'monthly':
            return t('settings.automation.summaryMonthly', { day: String(p.dayOfMonth), time });
        default:
            return cron;
    }
}

export function ScheduleBuilder({ value, onChange }: ScheduleBuilderProps): React.ReactElement {
    const { t } = useI18n();
    const [model, setModel] = useState<Parsed>(() => parseCron(value));
    // Raw cron text, only used in advanced mode.
    const [advancedCron, setAdvancedCron] = useState(value);

    // Re-parse when an external value arrives (e.g. opening the edit form).
    useEffect(() => {
        setModel(parseCron(value));
        setAdvancedCron(value);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value]);

    const update = (patch: Partial<Parsed>) => {
        const next = { ...model, ...patch };
        setModel(next);
        if (next.frequency !== 'advanced') {
            onChange(buildCron(next));
        }
    };

    const fieldLabel = (text: string) => (
        <label className="block font-bold tracking-wide text-brutal-black dark:text-white uppercase mb-1 text-xs">{text}</label>
    );

    // Match BrutalSelect's chrome (border-3 + 2px drop shadow) so the schedule
    // inputs sit consistently beside the Repeat dropdown.
    const brutalInput =
        'bg-white dark:bg-zinc-800 dark:text-white border-3 border-brutal-black px-3 py-2 font-bold text-sm focus:outline-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]';

    const numberInput = (val: number, min: number, max: number | undefined, onVal: (n: number) => void) => (
        <input
            type="number"
            min={min}
            {...(max !== undefined ? { max } : {})}
            value={val}
            onChange={e => {
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
            value={`${String(model.hour).padStart(2, '0')}:${String(model.minute).padStart(2, '0')}`}
            onChange={e => {
                const [h, m] = e.target.value.split(':').map(Number);
                update({ hour: h || 0, minute: m || 0 });
            }}
            className={brutalInput}
        />
    );

    const frequencyOptions = useMemo(() => [
        { value: 'minutes', label: t('settings.automation.freqMinutes') },
        { value: 'hourly', label: t('settings.automation.freqHourly') },
        { value: 'daily', label: t('settings.automation.freqDaily') },
        { value: 'weekly', label: t('settings.automation.freqWeekly') },
        { value: 'monthly', label: t('settings.automation.freqMonthly') },
        { value: 'advanced', label: t('settings.automation.freqAdvanced') },
    ], [t]);

    const weekdayOptions = useMemo(() => {
        const labels = t('settings.automation.weekdays').split(',');
        return WEEKDAYS.map((d, i) => ({ value: d, label: labels[i] ?? d }));
    }, [t]);

    return (
        <div className="space-y-2">
            <div className="flex flex-wrap gap-3 items-end">
                <BrutalSelect
                    value={model.frequency}
                    onChange={val => {
                        const freq = val as Frequency;
                        if (freq === 'advanced') {
                            setModel({ ...model, frequency: freq });
                            // Seed advanced box with the current built cron so nothing is lost.
                            const seeded = advancedCron || buildCron(model);
                            setAdvancedCron(seeded);
                            onChange(seeded);
                        } else {
                            update({ frequency: freq });
                        }
                    }}
                    options={frequencyOptions}
                    label={t('settings.automation.repeat')}
                    className="w-44"
                />

                {model.frequency === 'minutes' && (
                    <div>
                        {fieldLabel(t('settings.automation.intervalLabel'))}
                        {numberInput(model.interval, 1, undefined, n => update({ interval: n }))}
                    </div>
                )}

                {model.frequency === 'hourly' && (
                    <div>
                        {fieldLabel(t('settings.automation.atMinuteLabel'))}
                        {numberInput(model.minute, 0, 59, n => update({ minute: n }))}
                    </div>
                )}

                {model.frequency === 'weekly' && (
                    <div className="flex items-end gap-2 flex-wrap">
                        <BrutalMultiSelect
                            value={model.weekdays}
                            onChange={days => update({ weekdays: days.length ? days : model.weekdays })}
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

                {model.frequency === 'monthly' && (
                    <div>
                        {fieldLabel(t('settings.automation.onDayOfMonthLabel'))}
                        {numberInput(model.dayOfMonth, 1, 31, n => update({ dayOfMonth: n }))}
                    </div>
                )}

                {(model.frequency === 'daily' || model.frequency === 'weekly' || model.frequency === 'monthly') && (
                    <div>
                        {fieldLabel(t('settings.automation.atTimeLabel'))}
                        {timeInput}
                    </div>
                )}
            </div>

            {model.frequency === 'advanced' ? (
                <div className="space-y-1">
                    <input
                        value={advancedCron}
                        onChange={e => { setAdvancedCron(e.target.value); onChange(e.target.value); }}
                        placeholder={t('settings.automation.cronExprPlaceholder')}
                        className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500"
                    />
                    <p className="text-[11px] text-neutral-500 dark:text-neutral-400">{t('settings.automation.advancedHint')}</p>
                </div>
            ) : (
                <p className="text-xs text-neutral-600 dark:text-neutral-300">
                    {describeCron(buildCron(model), t)}
                </p>
            )}
        </div>
    );
}
