import React, { useState } from 'react';
import type { A2UIForm, A2UIFormField } from '../../../types/a2ui';
import { BrutalButton } from '../../BrutalButton';

interface Props {
  component: A2UIForm;
  onAction: (action: string, context: Record<string, unknown>) => void;
}

const inputBase =
  'w-full border-2 border-brutal-black px-3 py-2 text-sm bg-white dark:bg-zinc-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brutal-yellow';

// ── Inline single-select list (no portal — safe inside canvas) ────────────
function SelectOptionList({
  options,
  value,
  onChange,
  allowFreeText,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
  allowFreeText?: boolean;
}) {
  const isOther = allowFreeText && value !== '' && !options.includes(value);
  const [otherText, setOtherText] = React.useState(isOther ? value : '');
  const [otherActive, setOtherActive] = React.useState(isOther);

  return (
    <div className="flex flex-col border-2 border-brutal-black overflow-hidden">
      {options.map((opt, i) => (
        <button
          key={opt}
          type="button"
          onClick={() => { setOtherActive(false); onChange(opt); }}
          className={[
            'flex items-center justify-between px-4 py-3 text-sm font-bold text-left transition-colors',
            'border-t-2 border-brutal-black first:border-t-0',
            value === opt && !otherActive
              ? 'bg-brutal-yellow text-brutal-black'
              : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700',
          ].join(' ')}
        >
          <span>{opt}</span>
          <span className="text-xs font-mono text-neutral-400 border-2 border-neutral-300 dark:border-neutral-600 w-6 h-6 flex items-center justify-center shrink-0">
            {i + 1}
          </span>
        </button>
      ))}
      {allowFreeText && (
        <div className={[
          'border-t-2 border-brutal-black transition-colors',
          otherActive ? 'bg-brutal-yellow' : 'bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700',
        ].join(' ')}>
          <button
            type="button"
            onClick={() => { setOtherActive(true); onChange(otherText); }}
            className="flex items-center justify-between px-4 py-3 text-sm font-bold text-left w-full"
          >
            <span className={otherActive ? 'text-brutal-black' : 'text-neutral-400 dark:text-neutral-500'}>
              Type something else…
            </span>
            <span className="text-xs font-mono text-neutral-400 border-2 border-neutral-300 dark:border-neutral-600 w-6 h-6 flex items-center justify-center shrink-0">
              {options.length + 1}
            </span>
          </button>
          {otherActive && (
            <div className="px-4 pb-3">
              <input
                autoFocus
                type="text"
                className="w-full border-2 border-brutal-black px-3 py-2 text-sm bg-white dark:bg-zinc-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brutal-black"
                placeholder="Type your answer…"
                value={otherText}
                onChange={e => { setOtherText(e.target.value); onChange(e.target.value); }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Inline multi-select list with optional free-text last item ─────────────
function MultiSelectList({
  options,
  value,
  onChange,
  allowFreeText,
}: {
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
  allowFreeText?: boolean;
}) {
  const otherValue = value.find(v => !options.includes(v)) ?? '';
  const [otherText, setOtherText] = React.useState(otherValue);
  const otherChecked = otherValue !== '';

  const toggle = (opt: string) => {
    onChange(value.includes(opt) ? value.filter(v => v !== opt) : [...value, opt]);
  };

  const handleOtherToggle = () => {
    if (otherChecked) {
      setOtherText('');
      onChange(value.filter(v => options.includes(v)));
    } else {
      // just activate the text input; value updated as user types
    }
  };

  const handleOtherText = (text: string) => {
    setOtherText(text);
    const base = value.filter(v => options.includes(v));
    onChange(text ? [...base, text] : base);
  };

  return (
    <div className="flex flex-col border-2 border-brutal-black overflow-hidden">
      {options.map((opt, i) => {
        const active = value.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={[
              'flex items-center gap-3 px-4 py-3 text-sm font-bold text-left transition-colors',
              i > 0 ? 'border-t-2 border-brutal-black' : '',
              active
                ? 'bg-brutal-yellow text-brutal-black'
                : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700',
            ].join(' ')}
          >
            <div className={`w-4 h-4 border-2 border-brutal-black flex items-center justify-center shrink-0 ${active ? 'bg-brutal-black' : 'bg-white dark:bg-zinc-900'}`}>
              {active && <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
            </div>
            <span className="flex-1">{opt}</span>
            <span className="text-xs font-mono text-neutral-400 border-2 border-neutral-300 dark:border-neutral-600 w-6 h-6 flex items-center justify-center shrink-0">{i + 1}</span>
          </button>
        );
      })}
      {allowFreeText && (
        <div className={['border-t-2 border-brutal-black', otherChecked ? 'bg-brutal-yellow' : 'bg-white dark:bg-zinc-800'].join(' ')}>
          <button
            type="button"
            onClick={handleOtherToggle}
            className="flex items-center gap-3 px-4 py-3 text-sm font-bold text-left w-full"
          >
            <div className={`w-4 h-4 border-2 border-brutal-black flex items-center justify-center shrink-0 ${otherChecked ? 'bg-brutal-black' : 'bg-white dark:bg-zinc-900'}`}>
              {otherChecked && <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
            </div>
            <span className={`flex-1 ${otherChecked ? 'text-brutal-black' : 'text-neutral-400 dark:text-neutral-500'}`}>
              Type something else…
            </span>
            <span className="text-xs font-mono text-neutral-400 border-2 border-neutral-300 dark:border-neutral-600 w-6 h-6 flex items-center justify-center shrink-0">{options.length + 1}</span>
          </button>
          {(otherChecked || otherText !== '') && (
            <div className="px-4 pb-3">
              <input
                autoFocus
                type="text"
                className="w-full border-2 border-brutal-black px-3 py-2 text-sm bg-white dark:bg-zinc-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brutal-black"
                placeholder="Type your answer…"
                value={otherText}
                onChange={e => handleOtherText(e.target.value)}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Per-field input renderer ──────────────────────────────────────────────
interface FieldInputProps {
  field: A2UIFormField;
  value: unknown;
  onChange: (val: unknown) => void;
}

function FieldInput({ field, value, onChange }: FieldInputProps) {
  const type = field.type ?? 'text';

  if (type === 'textarea') {
    return (
      <textarea
        className={`${inputBase} min-h-[80px] resize-y`}
        placeholder={field.placeholder}
        value={String(value ?? '')}
        onChange={e => onChange(e.target.value)}
        required={field.required}
      />
    );
  }

  if (type === 'select') {
    return (
      <SelectOptionList
        options={field.options ?? []}
        value={String(value ?? '')}
        allowFreeText={field.allow_free_text}
        onChange={v => onChange(v)}
      />
    );
  }

  if (type === 'multiselect') {
    const selected = Array.isArray(value) ? (value as string[]) : [];
    return (
      <MultiSelectList
        options={field.options ?? []}
        value={selected}
        onChange={vals => onChange(vals)}
        allowFreeText={field.allow_free_text}
      />
    );
  }

  if (type === 'checkbox') {
    const checked = Boolean(value);
    return (
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={[
          'flex items-center gap-3 px-3 py-2 border-2 border-brutal-black text-sm font-bold transition-all w-full text-left',
          checked
            ? 'bg-brutal-yellow text-brutal-black'
            : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700',
        ].join(' ')}
      >
        <div
          className={`w-4 h-4 border-2 border-brutal-black flex items-center justify-center shrink-0 ${checked ? 'bg-brutal-black' : 'bg-white dark:bg-zinc-900'}`}
        >
          {checked && (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          )}
        </div>
        <span>{field.label}</span>
      </button>
    );
  }

  if (type === 'number') {
    return (
      <input
        type="number"
        className={inputBase}
        placeholder={field.placeholder}
        value={value == null ? '' : String(value)}
        onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        required={field.required}
      />
    );
  }

  // default: text
  return (
    <input
      type="text"
      className={inputBase}
      placeholder={field.placeholder}
      value={String(value ?? '')}
      onChange={e => onChange(e.target.value)}
      required={field.required}
    />
  );
}

// ── Paged (one question per page) ─────────────────────────────────────────
interface PagedFormProps {
  component: A2UIForm;
  values: Record<string, unknown>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, unknown>>>;
  onSubmit: () => void;
}

function PagedForm({ component, values, setValues, onSubmit }: PagedFormProps) {
  const fields = component.fields ?? [];
  const [page, setPage] = useState(0);
  const total = fields.length;
  const field = fields[page];
  const isLast = page === total - 1;

  const hasValue = (): boolean => {
    const val = values[field.name];
    if (field.type === 'multiselect') return Array.isArray(val) && (val as string[]).length > 0;
    return val !== '' && val != null;
  };

  const advance = () => { if (isLast) onSubmit(); else setPage(p => p + 1); };
  const skip = () => advance(); // skip this question, move to next (or submit)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-bold text-brutal-black dark:text-white leading-snug flex-1">
          {field.label}
          {field.required && <span className="text-red-500 ml-1">*</span>}
        </p>
        {total > 1 && (
          <span className="text-xs font-mono text-neutral-400 shrink-0">{page + 1}/{total}</span>
        )}
      </div>

      <FieldInput
        field={field}
        value={values[field.name]}
        onChange={val => setValues(prev => ({ ...prev, [field.name]: val }))}
      />

      <div className="flex items-center gap-2">
        {page > 0 && (
          <BrutalButton type="button" variant="default" size="sm" onClick={() => setPage(p => p - 1)}>
            ← Back
          </BrutalButton>
        )}
        <BrutalButton type="button" variant="ghost" size="sm" onClick={skip}>
          Skip
        </BrutalButton>
        <div className="flex-1" />
        <BrutalButton
          type="button"
          variant={isLast ? 'warning' : 'default'}
          size="sm"
          onClick={advance}
          disabled={!hasValue()}
        >
          {isLast ? (component.submit_label ?? 'Submit') : 'Next →'}
        </BrutalButton>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────
export const A2UIFormComponent: React.FC<Props> = ({ component, onAction }) => {
  const fields = component.fields ?? [];

  const initialValues = Object.fromEntries(
    fields.map(f => [
      f.name,
      f.type === 'multiselect'
        ? (Array.isArray(f.default) ? f.default : [])
        : (f.default ?? ''),
    ])
  );

  const [values, setValues] = useState<Record<string, unknown>>(initialValues);

  const submit = () => onAction(component.action || 'submit', values);

  if (component.paged) {
    return <PagedForm component={component} values={values} setValues={setValues} onSubmit={submit} />;
  }

  return (
    <form
      onSubmit={e => { e.preventDefault(); submit(); }}
      className="flex flex-col gap-4"
    >
      {fields.map(field => (
        <div key={field.name} className="flex flex-col gap-1">
          {field.type !== 'checkbox' && (
            <label className="text-xs font-bold uppercase tracking-wide text-brutal-black dark:text-white">
              {field.label}
              {field.required && <span className="text-red-500 ml-1">*</span>}
            </label>
          )}
          <FieldInput
            field={field}
            value={values[field.name]}
            onChange={val => setValues(prev => ({ ...prev, [field.name]: val }))}
          />
        </div>
      ))}
      <BrutalButton type="submit" variant="warning" className="mt-2 w-full justify-center uppercase tracking-wide">
        {component.submit_label ?? 'Submit'}
      </BrutalButton>
    </form>
  );
};
