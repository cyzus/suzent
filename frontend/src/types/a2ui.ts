/**
 * A2UI type definitions — mirrors the backend Pydantic models in src/suzent/a2ui/models.py.
 * The `type` field is the discriminator for the component union.
 */

// ── Leaf Components ──────────────────────────────────────────────────

export interface A2UIText {
  type: 'text';
  content: string;
  variant?: 'body' | 'heading' | 'subheading' | 'caption' | 'code';
  markdown?: boolean;
}

export interface A2UIBadge {
  type: 'badge';
  label: string;
  color?: 'default' | 'success' | 'warning' | 'error' | 'info';
}

export interface A2UIButton {
  type: 'button';
  label: string;
  action: string;
  context?: Record<string, unknown>;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
}

export interface A2UITableColumn {
  key: string;
  label: string;
  width?: string;
}

export interface A2UITable {
  type: 'table';
  columns: A2UITableColumn[];
  rows: Record<string, unknown>[];
}

export interface A2UIFormField {
  name: string;
  label: string;
  type?: 'text' | 'number' | 'select' | 'multiselect' | 'checkbox' | 'textarea';
  options?: string[];
  allow_free_text?: boolean;
  required?: boolean;
  default?: unknown;
  placeholder?: string;
}

export interface A2UIForm {
  type: 'form';
  fields: A2UIFormField[];
  submit_label?: string;
  action: string;
  paged?: boolean;
}

export interface A2UIList {
  type: 'list';
  items: string[];
  ordered?: boolean;
}

export interface A2UIProgress {
  type: 'progress';
  value: number;
  label?: string;
}

export interface A2UIDivider {
  type: 'divider';
}

// ── Container Components ─────────────────────────────────────────────

export interface A2UICard {
  type: 'card';
  title?: string;
  children: A2UIComponent[];
}

export interface A2UIColumns {
  type: 'columns';
  children: A2UIComponent[];
  ratios?: number[];
}

export interface A2UIStack {
  type: 'stack';
  children: A2UIComponent[];
  gap?: 'sm' | 'md' | 'lg';
}

// ── Union ────────────────────────────────────────────────────────────

export type A2UIComponent =
  | A2UIText
  | A2UIBadge
  | A2UIButton
  | A2UITable
  | A2UIForm
  | A2UIList
  | A2UIProgress
  | A2UIDivider
  | A2UICard
  | A2UIColumns
  | A2UIStack;

// ── Top-level Surface ────────────────────────────────────────────────

export interface A2UISurface {
  id: string;
  title?: string;
  component: A2UIComponent;
  /** "canvas" (default): sidebar panel. "inline": inside the chat message. */
  target?: 'canvas' | 'inline';
  /** If true, the surface was rendered by ask_question and the agent is blocked
   *  awaiting a response. Interactions should POST to /canvas/{chatId}/answer
   *  instead of /canvas/{chatId}/action. */
  deferred?: boolean;
}
