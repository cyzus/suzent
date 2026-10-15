import React, { useState } from 'react';
import type { A2UIForm, A2UIFormField } from '../../../types/a2ui';
import { BrutalButton } from '../../BrutalButton';
import { useI18n } from '../../../i18n';

interface Props {
  component: A2UIForm;
  onAction: (action: string, context: Record<string, unknown>) => void;
}

const inputBase =
  'w-full border-2 border-brutal-black px-3 py-2 text-sm bg-white dark:bg-zinc-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brutal-yellow';

function isTypingTarget(target: EventTarget): boolean {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
}

// Number keys 1–9 pick the option with that badge; returns its index or null.
function shortcutIndex(e: React.KeyboardEvent, count: number): number | null {
  if (e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(e.target)) return null;
  const n = Number(e.key);
  if (!Number.isInteger(n) || n < 1 || n > Math.min(count, 9)) return null;
  return n - 1;
}

function useFocusOnMount(autoFocus: boolean | undefined): React.RefObject<HTMLDivElement> {
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (autoFocus) ref.current?.focus({ preventScroll: true });
  }, [autoFocus]);
  return ref;
}

function OtherInput({
  inputRef,
  value,
  onChange,
  onEscape,
}: {
  inputRef: React.RefObject<HTMLInputElement>;
  value: string;
  onChange: (v: string) => void;
  onEscape: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="px-4 pb-3">
      <input
        ref={inputRef}
        autoFocus
        type="text"
        className="w-full border-2 border-brutal-black px-3 py-2 text-sm bg-white dark:bg-zinc-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brutal-black"
        placeholder={t('a2uiForm.otherPlaceholder')}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.preventDefault();
            onEscape();
          }
        }}
      />
    </div>
  );
}

// ── Inline single-select list (no portal — safe inside canvas) ────────────
function SelectOptionList({
  options,
  value,
  onChange,
  allowFreeText,
  autoFocus,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
  allowFreeText?: boolean;
  autoFocus?: boolean;
}) {
  const { t } = useI18n();
  const isOther = allowFreeText && value !== '' && !options.includes(value);
  const [otherText, setOtherText] = React.useState(isOther ? value : '');
  const [otherActive, setOtherActive] = React.useState(isOther);
  const rootRef = useFocusOnMount(autoFocus);
  const otherInputRef = React.useRef<HTMLInputElement>(null);

  const choose = (i: number) => {
    if (i < options.length) {
      setOtherActive(false);
      onChange(options[i]);
      return;
    }
    setOtherActive(true);
    onChange(otherText);
    otherInputRef.current?.focus();
  };

  return (
    <div
      ref={rootRef}
      tabIndex={-1}
      onKeyDown={(e) => {
        const i = shortcutIndex(e, options.length + (allowFreeText ? 1 : 0));
        if (i === null) return;
        e.preventDefault();
        choose(i);
      }}
      className="flex flex-col border-2 border-brutal-black overflow-hidden focus:outline-none"
    >
      {options.map((opt, i) => (
        <button
          key={opt}
          type="button"
          onClick={() => choose(i)}
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
        <div
          className={[
            'border-t-2 border-brutal-black transition-colors',
            otherActive
              ? 'bg-brutal-yellow'
              : 'bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700',
          ].join(' ')}
        >
          <button
            type="button"
            onClick={() => choose(options.length)}
            className="flex items-center justify-between px-4 py-3 text-sm font-bold text-left w-full"
          >
            <span
              className={
                otherActive ? 'text-brutal-black' : 'text-neutral-400 dark:text-neutral-500'
              }
            >
              {t('a2uiForm.typeSomethingElse')}
            </span>
            <span className="text-xs font-mono text-neutral-400 border-2 border-neutral-300 dark:border-neutral-600 w-6 h-6 flex items-center justify-center shrink-0">
              {options.length + 1}
            </span>
          </button>
          {otherActive && (
            <OtherInput
              inputRef={otherInputRef}
              value={otherText}
              onChange={(text) => {
                setOtherText(text);
                onChange(text);
              }}
              onEscape={() => rootRef.current?.focus()}
            />
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
  autoFocus,
}: {
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
  allowFreeText?: boolean;
  autoFocus?: boolean;
}) {
  const { t } = useI18n();
  const initialOther = value.find((v) => !options.includes(v)) ?? '';
  const [otherText, setOtherText] = React.useState(initialOther);
  const [otherActive, setOtherActive] = React.useState(initialOther !== '');
  const rootRef = useFocusOnMount(autoFocus);
  const otherInputRef = React.useRef<HTMLInputElement>(null);
  const base = value.filter((v) => options.includes(v));

  const toggle = (opt: string) => {
    onChange(value.includes(opt) ? value.filter((v) => v !== opt) : [...value, opt]);
  };

  const toggleOther = () => {
    if (otherActive) {
      setOtherActive(false);
      setOtherText('');
      onChange(base);
      rootRef.current?.focus();
      return;
    }
    setOtherActive(true);
    otherInputRef.current?.focus();
  };

  const handleOtherText = (text: string) => {
    setOtherText(text);
    onChange(text ? [...base, text] : base);
  };

  return (
    <div
      ref={rootRef}
      tabIndex={-1}
      onKeyDown={(e) => {
        const i = shortcutIndex(e, options.length + (allowFreeText ? 1 : 0));
        if (i === null) return;
        e.preventDefault();
        if (i < options.length) toggle(options[i]);
        else toggleOther();
      }}
      className="flex flex-col border-2 border-brutal-black overflow-hidden focus:outline-none"
    >
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
            <div
              className={`w-4 h-4 border-2 border-brutal-black flex items-center justify-center shrink-0 ${active ? 'bg-brutal-black' : 'bg-white dark:bg-zinc-900'}`}
            >
              {active && (
                <svg
                  className="w-3 h-3 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={4}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
            <span className="flex-1">{opt}</span>
            <span className="text-xs font-mono text-neutral-400 border-2 border-neutral-300 dark:border-neutral-600 w-6 h-6 flex items-center justify-center shrink-0">
              {i + 1}
            </span>
          </button>
        );
      })}
      {allowFreeText && (
        <div
          className={[
            'border-t-2 border-brutal-black',
            otherActive ? 'bg-brutal-yellow' : 'bg-white dark:bg-zinc-800',
          ].join(' ')}
        >
          <button
            type="button"
            onClick={toggleOther}
            className="flex items-center gap-3 px-4 py-3 text-sm font-bold text-left w-full"
          >
            <div
              className={`w-4 h-4 border-2 border-brutal-black flex items-center justify-center shrink-0 ${otherActive ? 'bg-brutal-black' : 'bg-white dark:bg-zinc-900'}`}
            >
              {otherActive && (
                <svg
                  className="w-3 h-3 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={4}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
            <span
              className={`flex-1 ${otherActive ? 'text-brutal-black' : 'text-neutral-400 dark:text-neutral-500'}`}
            >
              {t('a2uiForm.typeSomethingElse')}
            </span>
            <span className="text-xs font-mono text-neutral-400 border-2 border-neutral-300 dark:border-neutral-600 w-6 h-6 flex items-center justify-center shrink-0">
              {options.length + 1}
            </span>
          </button>
          {otherActive && (
            <OtherInput
              inputRef={otherInputRef}
              value={otherText}
              onChange={handleOtherText}
              onEscape={() => rootRef.current?.focus()}
            />
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
  autoFocus?: boolean;
}

function FieldInput({ field, value, onChange, autoFocus }: FieldInputProps) {
  const type = field.type ?? 'text';

  if (type === 'textarea') {
    return (
      <textarea
        autoFocus={autoFocus}
        className={`${inputBase} min-h-[80px] resize-y`}
        placeholder={field.placeholder}
        value={String(value ?? '')}
        onChange={(e) => onChange(e.target.value)}
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
        autoFocus={autoFocus}
        onChange={(v) => onChange(v)}
      />
    );
  }

  if (type === 'multiselect') {
    const selected = Array.isArray(value) ? (value as string[]) : [];
    return (
      <MultiSelectList
        options={field.options ?? []}
        value={selected}
        onChange={(vals) => onChange(vals)}
        allowFreeText={field.allow_free_text}
        autoFocus={autoFocus}
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
            <svg
              className="w-3 h-3 text-white"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={4}
            >
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
        onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        required={field.required}
      />
    );
  }

  // default: text
  return (
    <input
      autoFocus={autoFocus}
      type="text"
      className={inputBase}
      placeholder={field.placeholder}
      value={String(value ?? '')}
      onChange={(e) => onChange(e.target.value)}
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
  const { t } = useI18n();
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

  const advance = () => {
    if (isLast) onSubmit();
    else setPage((p) => p + 1);
  };
  const skip = () => advance(); // skip this question, move to next (or submit)
  const navRef = React.useRef<HTMLDivElement>(null);

  // Enter moves on from anywhere in the question (Shift+Enter keeps a newline);
  // the nav buttons keep their own Enter so Back/Skip still work from the keyboard.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return;
    if (navRef.current?.contains(e.target as Node)) return;
    e.preventDefault();
    if (hasValue()) advance();
  };

  return (
    <div className="flex flex-col gap-4" onKeyDown={handleKeyDown}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-bold text-brutal-black dark:text-white leading-snug flex-1">
          {field.label}
          {field.required && <span className="text-red-500 ml-1">*</span>}
        </p>
        {total > 1 && (
          <span className="text-xs font-mono text-neutral-400 shrink-0">
            {page + 1}/{total}
          </span>
        )}
      </div>

      <FieldInput
        key={field.name}
        field={field}
        value={values[field.name]}
        onChange={(val) => setValues((prev) => ({ ...prev, [field.name]: val }))}
        autoFocus
      />

      <div ref={navRef} className="flex items-center gap-2">
        {page > 0 && (
          <BrutalButton
            type="button"
            variant="default"
            size="sm"
            onClick={() => setPage((p) => p - 1)}
          >
            {t('a2uiForm.back')}
          </BrutalButton>
        )}
        <BrutalButton type="button" variant="ghost" size="sm" onClick={skip}>
          {t('a2uiForm.skip')}
        </BrutalButton>
        <div className="flex-1" />
        <BrutalButton
          type="button"
          variant={isLast ? 'warning' : 'default'}
          size="sm"
          onClick={advance}
          disabled={!hasValue()}
        >
          {isLast ? (component.submit_label ?? t('a2uiForm.submit')) : t('a2uiForm.next')}
        </BrutalButton>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────
export const A2UIFormComponent: React.FC<Props> = ({ component, onAction }) => {
  const fields = component.fields ?? [];

  const initialValues = Object.fromEntries(
    fields.map((f) => [
      f.name,
      f.type === 'multiselect' ? (Array.isArray(f.default) ? f.default : []) : (f.default ?? ''),
    ])
  );

  const [values, setValues] = useState<Record<string, unknown>>(initialValues);

  const submit = () => onAction(component.action || 'submit', values);

  if (component.paged) {
    return (
      <PagedForm component={component} values={values} setValues={setValues} onSubmit={submit} />
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex flex-col gap-4"
    >
      {fields.map((field) => (
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
            onChange={(val) => setValues((prev) => ({ ...prev, [field.name]: val }))}
          />
        </div>
      ))}
      <BrutalButton
        type="submit"
        variant="warning"
        className="mt-2 w-full justify-center uppercase tracking-wide"
      >
        {component.submit_label ?? 'Submit'}
      </BrutalButton>
    </form>
  );
};
