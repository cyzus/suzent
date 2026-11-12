/**
 * Convert key presses to Tauri global-shortcut accelerators
 * ("CommandOrControl+Shift+Space") and back to keycaps for display.
 */

export interface KeyPress {
  code: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
}

export type AcceleratorResult =
  | { kind: 'partial'; modifiers: string[] }
  | { kind: 'needs_modifier' }
  | { kind: 'unsupported' }
  | { kind: 'done'; accelerator: string };

const MODIFIER_CODES = new Set([
  'ControlLeft',
  'ControlRight',
  'MetaLeft',
  'MetaRight',
  'AltLeft',
  'AltRight',
  'ShiftLeft',
  'ShiftRight',
  'OSLeft',
  'OSRight',
]);

const NAMED_KEYS: Record<string, string> = {
  Space: 'Space',
  Enter: 'Enter',
  Tab: 'Tab',
  Backspace: 'Backspace',
  Delete: 'Delete',
  Insert: 'Insert',
  Home: 'Home',
  End: 'End',
  PageUp: 'PageUp',
  PageDown: 'PageDown',
  ArrowUp: 'Up',
  ArrowDown: 'Down',
  ArrowLeft: 'Left',
  ArrowRight: 'Right',
  Backquote: 'Backquote',
  Minus: 'Minus',
  Equal: 'Equal',
  BracketLeft: 'BracketLeft',
  BracketRight: 'BracketRight',
  Backslash: 'Backslash',
  Semicolon: 'Semicolon',
  Quote: 'Quote',
  Comma: 'Comma',
  Period: 'Period',
  Slash: 'Slash',
};

function keyName(code: string): string | null {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3);
  if (/^Digit[0-9]$/.test(code)) return code.slice(5);
  if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) return code;
  return NAMED_KEYS[code] ?? null;
}

function modifiers(press: KeyPress, mac: boolean): string[] {
  const names: string[] = [];
  // The platform's main modifier maps to CommandOrControl so the shortcut
  // stays the same when the settings sync to another OS.
  if (mac ? press.metaKey : press.ctrlKey) names.push('CommandOrControl');
  if (mac && press.ctrlKey) names.push('Control');
  if (!mac && press.metaKey) names.push('Super');
  if (press.altKey) names.push('Alt');
  if (press.shiftKey) names.push('Shift');
  return names;
}

/** What a keydown means while recording a shortcut. */
export function acceleratorFromKeyPress(press: KeyPress, mac: boolean): AcceleratorResult {
  const held = modifiers(press, mac);
  if (MODIFIER_CODES.has(press.code)) return { kind: 'partial', modifiers: held };
  const key = keyName(press.code);
  if (!key) return { kind: 'unsupported' };
  const functionKey = /^F\d+$/.test(key);
  // Shift alone still types text, so it would steal ordinary keystrokes.
  const typing = held.length === 0 || (held.length === 1 && held[0] === 'Shift');
  if (typing && !functionKey) return { kind: 'needs_modifier' };
  return { kind: 'done', accelerator: [...held, key].join('+') };
}

const MAC_CAPS: Record<string, string> = {
  CommandOrControl: '⌘',
  CmdOrCtrl: '⌘',
  Command: '⌘',
  Cmd: '⌘',
  Super: '⌘',
  Meta: '⌘',
  Control: '⌃',
  Ctrl: '⌃',
  Alt: '⌥',
  Option: '⌥',
  Shift: '⇧',
};

const PC_CAPS: Record<string, string> = {
  CommandOrControl: 'Ctrl',
  CmdOrCtrl: 'Ctrl',
  Control: 'Ctrl',
  Ctrl: 'Ctrl',
  Super: 'Win',
  Meta: 'Win',
  Command: 'Win',
  Cmd: 'Win',
  Alt: 'Alt',
  Option: 'Alt',
  Shift: 'Shift',
};

const KEY_CAPS: Record<string, string> = {
  Up: '↑',
  Down: '↓',
  Left: '←',
  Right: '→',
  Backquote: '`',
  Minus: '-',
  Equal: '=',
  BracketLeft: '[',
  BracketRight: ']',
  Backslash: '\\',
  Semicolon: ';',
  Quote: "'",
  Comma: ',',
  Period: '.',
  Slash: '/',
};

/** Keycap labels for an accelerator or a list of held modifiers. */
export function acceleratorKeycaps(parts: string[], mac: boolean): string[] {
  const caps = mac ? MAC_CAPS : PC_CAPS;
  return parts
    .filter(Boolean)
    .map((part) => caps[part] ?? KEY_CAPS[part] ?? part.replace(/^(Key|Digit)/, ''));
}
