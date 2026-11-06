import React, { useId } from 'react';

interface BrutalRangeProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  valueText: string;
  onChange: (value: number) => void;
  disabled?: boolean;
}

export function BrutalRange({
  label,
  value,
  min,
  max,
  step,
  valueText,
  onChange,
  disabled = false,
}: BrutalRangeProps): React.ReactElement {
  const id = useId();
  const progress = max > min ? Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100)) : 0;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 text-xs font-bold uppercase tracking-wide">
        <label htmlFor={id}>{label}</label>
        <output
          htmlFor={id}
          className="font-mono tabular-nums text-neutral-600 dark:text-neutral-300"
        >
          {valueText}
        </output>
      </div>
      <input
        id={id}
        type="range"
        className="brutal-range"
        style={{ '--range-progress': `${progress}%` } as React.CSSProperties}
        min={min}
        max={max}
        step={step}
        value={value}
        aria-valuetext={valueText}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}
