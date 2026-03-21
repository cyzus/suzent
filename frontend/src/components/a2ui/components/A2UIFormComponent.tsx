import React, { useState } from 'react';
import type { A2UIForm, A2UIFormField } from '../../../types/a2ui';

interface Props {
  component: A2UIForm;
  onAction: (action: string, context: Record<string, unknown>) => void;
}

function FieldInput({ field, value, onChange }: {
  field: A2UIFormField;
  value: unknown;
  onChange: (val: unknown) => void;
}) {
  const base = "w-full border-2 border-brutal-black px-3 py-2 text-sm bg-white dark:bg-zinc-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brutal-yellow";

  switch (field.type ?? 'text') {
    case 'textarea':
      return (
        <textarea
          className={`${base} min-h-[80px] resize-y`}
          placeholder={field.placeholder}
          value={String(value ?? '')}
          onChange={e => onChange(e.target.value)}
          required={field.required}
        />
      );
    case 'select':
      return (
        <select
          className={base}
          value={String(value ?? '')}
          onChange={e => onChange(e.target.value)}
          required={field.required}
        >
          <option value="">— select —</option>
          {(field.options ?? []).map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      );
    case 'checkbox':
      return (
        <input
          type="checkbox"
          className="w-4 h-4 border-2 border-brutal-black accent-brutal-yellow"
          checked={Boolean(value)}
          onChange={e => onChange(e.target.checked)}
        />
      );
    case 'number':
      return (
        <input
          type="number"
          className={base}
          placeholder={field.placeholder}
          value={value == null ? '' : String(value)}
          onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}
          required={field.required}
        />
      );
    default:
      return (
        <input
          type="text"
          className={base}
          placeholder={field.placeholder}
          value={String(value ?? '')}
          onChange={e => onChange(e.target.value)}
          required={field.required}
        />
      );
  }
}

export const A2UIFormComponent: React.FC<Props> = ({ component, onAction }) => {
  const initialValues = Object.fromEntries(
    (component.fields ?? []).map(f => [f.name, f.default ?? ''])
  );
  const [values, setValues] = useState<Record<string, unknown>>(initialValues);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAction(component.action || 'submit', values);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {(component.fields ?? []).map(field => (
        <div key={field.name} className="flex flex-col gap-1">
          <label className="text-xs font-bold uppercase tracking-wide text-brutal-black dark:text-white">
            {field.label}
            {field.required && <span className="text-red-500 ml-1">*</span>}
          </label>
          <FieldInput
            field={field}
            value={values[field.name]}
            onChange={val => setValues(prev => ({ ...prev, [field.name]: val }))}
          />
        </div>
      ))}
      <button
        type="submit"
        className="mt-2 bg-brutal-yellow border-2 border-brutal-black px-4 py-2 text-sm font-bold uppercase tracking-wide
          hover:bg-yellow-300 active:translate-x-[1px] active:translate-y-[1px] transition-transform"
      >
        {component.submit_label ?? 'Submit'}
      </button>
    </form>
  );
};
