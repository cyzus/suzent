import React from 'react';

/**
 * A contenteditable input that renders `@[path]` file mentions as atomic,
 * non-editable chips (Slack / Linear / Claude Code style).
 *
 * Why contenteditable instead of a <textarea> + highlight overlay:
 *  - Backspace on a chip deletes the WHOLE mention, never leaving a
 *    half-deleted `@"Multi Agents` fragment behind.
 *  - The caret cannot drift, because text and chips live in a single layer
 *    (a transparent-overlay textarea has two layers that desync whenever a
 *    chip's rendered width differs from its raw text width).
 *  - Chips can have real borders/padding and show the full path.
 *
 * External contract mirrors a plain textarea: `value` is the serialized
 * string where each mention is `@[<path>]`, and `onChange(value)` fires with
 * that serialized string. The parent stays string-based and unaware of chips.
 */

const MENTION_TOKEN = /@\[([^\]]+)\]/g;

export interface MentionTextAreaHandle {
    focus: () => void;
    blur: () => void;
    /** Replace the `@…` query currently under the caret with a mention chip. */
    insertMention: (path: string, label: string) => void;
    /** The `@…` query text immediately before the caret, or null. */
    getActiveQuery: () => { query: string } | null;
    /** DOM rect of the caret, for positioning popups (unused for now). */
    element: HTMLDivElement | null;
}

interface MentionTextAreaProps {
    value: string;
    onChange: (value: string) => void;
    onKeyDown?: (e: React.KeyboardEvent<HTMLDivElement>) => void;
    onPaste?: (e: React.ClipboardEvent<HTMLDivElement>) => void;
    onCompositionStart?: () => void;
    onCompositionEnd?: () => void;
    /** Fired whenever the caret's active `@` query changes (or clears). */
    onQueryChange?: (query: string | null) => void;
    placeholder?: string;
    disabled?: boolean;
    className?: string;
    /** How to display a mention path inside its chip (e.g. show full path). */
    renderChipLabel?: (path: string) => string;
}

/**
 * Chip label: a compact form of the path. Short paths are shown whole; long
 * ones are middle-truncated (keep the leading root + trailing filename, elide
 * the middle) so the tag stays readable without hiding which file it is. The
 * full path is preserved on the chip's data attribute for serialization.
 */
const CHIP_LABEL_MAX = 40;

function defaultChipLabel(path: string): string {
    const normalized = path.replace(/\\/g, '/');
    if (normalized.length <= CHIP_LABEL_MAX) return normalized;

    const parts = normalized.split('/');
    const file = parts[parts.length - 1];
    const root = parts[0]; // '' for POSIX absolute, 'D:' for Windows, else first segment
    const head = root ? `${root}/` : '/';
    const ellipsis = '…/';

    // Prefer "root/…/file"; if the filename alone is still too long, truncate it.
    const candidate = `${head}${ellipsis}${file}`;
    if (candidate.length <= CHIP_LABEL_MAX) return candidate;

    const keep = Math.max(8, CHIP_LABEL_MAX - head.length - ellipsis.length - 1);
    return `${head}${ellipsis}…${file.slice(file.length - keep)}`;
}

/**
 * Build DOM children for a serialized string: plain text nodes interleaved
 * with atomic chip spans. Chips are `contentEditable=false` so the browser
 * treats them as a single deletable unit.
 */
function buildNodes(
    value: string,
    renderChipLabel: (path: string) => string,
): Node[] {
    const nodes: Node[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    MENTION_TOKEN.lastIndex = 0;
    while ((match = MENTION_TOKEN.exec(value)) !== null) {
        if (match.index > lastIndex) {
            nodes.push(document.createTextNode(value.slice(lastIndex, match.index)));
        }
        nodes.push(makeChip(match[1], renderChipLabel));
        lastIndex = match.index + match[0].length;
    }
    if (lastIndex < value.length) {
        nodes.push(document.createTextNode(value.slice(lastIndex)));
    }
    return nodes;
}

/** Basename of a virtual path, used as the fallback decompose query. */
function basename(path: string): string {
    const trimmed = path.replace(/\/+$/, '');
    const idx = trimmed.lastIndexOf('/');
    return idx >= 0 ? trimmed.slice(idx + 1) : trimmed;
}

function makeChip(
    path: string,
    renderChipLabel: (path: string) => string,
    name?: string,
): HTMLSpanElement {
    const chip = document.createElement('span');
    chip.setAttribute('data-mention-path', path);
    // The name the user picked, so backspacing a chip can decompose it back to
    // an editable `@name` query. Falls back to the path basename when a chip is
    // rebuilt from the serialized `@[path]` form (which carries no name).
    chip.setAttribute('data-mention-name', name ?? basename(path));
    chip.setAttribute('contenteditable', 'false');
    // Full path on hover, since the visible label may be middle-truncated.
    chip.setAttribute('title', path);
    chip.className =
        'inline-flex items-center align-baseline rounded-[3px] border-2 border-brutal-black dark:border-white ' +
        'bg-brutal-yellow dark:bg-yellow-600 text-brutal-black font-bold px-1 mx-px leading-tight ' +
        'whitespace-nowrap select-none cursor-default text-[0.9em]';
    chip.textContent = renderChipLabel(path);
    return chip;
}

/**
 * Serialize the editor DOM back to the `@[path]` string form. Chips become
 * `@[path]`; everything else contributes its text. Block boundaries (from
 * contenteditable inserting <div>/<br> on Enter) become newlines.
 */
function serialize(root: HTMLElement): string {
    let out = '';
    const walk = (node: Node, isBlockStart: boolean) => {
        if (node.nodeType === Node.TEXT_NODE) {
            out += node.textContent ?? '';
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        const el = node as HTMLElement;
        const path = el.getAttribute('data-mention-path');
        if (path != null) {
            out += `@[${path}]`;
            return;
        }
        if (el.tagName === 'BR') {
            out += '\n';
            return;
        }
        // A DIV/P block that isn't the very first line starts on a new line.
        const isBlock = el.tagName === 'DIV' || el.tagName === 'P';
        if (isBlock && !isBlockStart && out !== '' && !out.endsWith('\n')) {
            out += '\n';
        }
        let first = true;
        el.childNodes.forEach(child => {
            walk(child, first && isBlock);
            first = false;
        });
    };
    let first = true;
    root.childNodes.forEach(child => {
        walk(child, first);
        first = false;
    });
    return out;
}

/** The `@query` immediately before the caret within a text node, if any. */
function readActiveQuery(root: HTMLElement): string | null {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || !sel.isCollapsed) return null;
    const range = sel.getRangeAt(0);
    if (!root.contains(range.startContainer)) return null;
    if (range.startContainer.nodeType !== Node.TEXT_NODE) return null;

    const text = range.startContainer.textContent ?? '';
    const before = text.slice(0, range.startOffset);
    // `@` must start the input, follow whitespace, and the query has no `@`.
    const m = before.match(/(^|\s)@([^@]*)$/);
    if (!m) return null;
    return m[2];
}

function isChip(node: Node | null): node is HTMLElement {
    return (
        node != null &&
        node.nodeType === Node.ELEMENT_NODE &&
        (node as HTMLElement).hasAttribute('data-mention-path')
    );
}

/**
 * The node immediately to the LEFT of a collapsed caret, or null if there is
 * editable content (text) to delete first. Normalizes the several ways a
 * browser can report a caret adjacent to a non-editable chip:
 *  - text node, offset > 0  -> a char precedes the caret; not a chip boundary
 *  - text node, offset 0    -> look at the node's previous sibling
 *  - element container      -> look at childNodes[offset - 1]
 */
function nodeBeforeCollapsedCaret(root: HTMLElement): Node | null {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || !sel.isCollapsed) return null;
    const range = sel.getRangeAt(0);
    let { startContainer, startOffset } = range;
    if (!root.contains(startContainer)) return null;

    if (startContainer.nodeType === Node.TEXT_NODE) {
        if (startOffset > 0) return null; // a character precedes the caret
        return startContainer.previousSibling;
    }
    // Element container: the caret is between childNodes.
    if (startContainer.nodeType === Node.ELEMENT_NODE) {
        if (startOffset === 0) return null;
        return (startContainer as Element).childNodes[startOffset - 1] ?? null;
    }
    return null;
}

/**
 * If the caret sits immediately after a mention chip (collapsed selection),
 * return that chip — including when an empty text node was left between them
 * (which happens after the trailing space is deleted).
 */
function chipBeforeCollapsedCaret(root: HTMLElement): HTMLElement | null {
    let prev = nodeBeforeCollapsedCaret(root);
    // Skip over an empty text node the browser may leave adjacent to the chip.
    while (prev && prev.nodeType === Node.TEXT_NODE && (prev.textContent ?? '') === '') {
        prev = prev.previousSibling;
    }
    return isChip(prev) ? prev : null;
}

export const MentionTextArea = React.forwardRef<MentionTextAreaHandle, MentionTextAreaProps>(
    (
        {
            value,
            onChange,
            onKeyDown,
            onPaste,
            onCompositionStart,
            onCompositionEnd,
            onQueryChange,
            placeholder,
            disabled,
            className,
            renderChipLabel = defaultChipLabel,
        },
        ref,
    ) => {
        const divRef = React.useRef<HTMLDivElement | null>(null);
        // Guard against reconciling the DOM from `value` while the user is
        // actively typing (which would blow away the caret). We only rebuild
        // the DOM when `value` changes from OUTSIDE (e.g. programmatic clear).
        const lastSerializedRef = React.useRef<string>('');
        const isComposingRef = React.useRef(false);

        const emitChange = React.useCallback(() => {
            const el = divRef.current;
            if (!el) return;
            const next = serialize(el);
            lastSerializedRef.current = next;
            onChange(next);
            onQueryChange?.(readActiveQuery(el));
        }, [onChange, onQueryChange]);

        // Reconcile DOM when `value` is changed externally (clear, restore,
        // programmatic edits). Skip when it already matches what we serialized,
        // so ordinary typing never triggers a caret-destroying rebuild.
        React.useEffect(() => {
            const el = divRef.current;
            if (!el) return;
            if (value === lastSerializedRef.current) return;
            // Never rebuild mid-IME-composition; it would abort the composition
            // and drop the in-flight characters.
            if (isComposingRef.current) return;
            const nodes = buildNodes(value, renderChipLabel);
            el.replaceChildren(...nodes);
            lastSerializedRef.current = value;
            onQueryChange?.(readActiveQuery(el));
        }, [value, renderChipLabel, onQueryChange]);

        const insertMention = React.useCallback(
            (path: string, label: string) => {
                const el = divRef.current;
                if (!el) return;
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return;
                const range = sel.getRangeAt(0);
                if (!el.contains(range.startContainer)) return;

                // Delete the `@query` text just before the caret.
                if (range.startContainer.nodeType === Node.TEXT_NODE) {
                    const textNode = range.startContainer as Text;
                    const before = (textNode.textContent ?? '').slice(0, range.startOffset);
                    const m = before.match(/(^|\s)@([^@]*)$/);
                    if (m) {
                        const queryStart = range.startOffset - m[2].length - 1; // include '@'
                        const delRange = document.createRange();
                        delRange.setStart(textNode, queryStart);
                        delRange.setEnd(textNode, range.startOffset);
                        delRange.deleteContents();
                        sel.removeAllRanges();
                        sel.addRange(delRange);
                    }
                }

                const insertRange = sel.getRangeAt(0);
                const chip = makeChip(path, renderChipLabel, label);
                const space = document.createTextNode(' ');
                insertRange.insertNode(space);
                insertRange.insertNode(chip);

                // Place caret after the trailing space.
                const after = document.createRange();
                after.setStartAfter(space);
                after.collapse(true);
                sel.removeAllRanges();
                sel.addRange(after);

                emitChange();
            },
            [emitChange, renderChipLabel],
        );

        // Turn a chip back into an editable `@name` query, caret at the end, so
        // the search dropdown reopens and the user can fix a typo and re-pick.
        const decomposeChip = React.useCallback(
            (chip: HTMLElement) => {
                const el = divRef.current;
                if (!el) return;
                const name = chip.getAttribute('data-mention-name') ?? '';
                const textNode = document.createTextNode(`@${name}`);
                chip.replaceWith(textNode);

                const sel = window.getSelection();
                if (sel) {
                    const caret = document.createRange();
                    caret.setStart(textNode, textNode.length);
                    caret.collapse(true);
                    sel.removeAllRanges();
                    sel.addRange(caret);
                }
                emitChange();
            },
            [emitChange],
        );

        React.useImperativeHandle(
            ref,
            () => ({
                focus: () => divRef.current?.focus(),
                blur: () => divRef.current?.blur(),
                insertMention,
                getActiveQuery: () => {
                    const q = divRef.current ? readActiveQuery(divRef.current) : null;
                    return q == null ? null : { query: q };
                },
                get element() {
                    return divRef.current;
                },
            }),
            [insertMention],
        );

        const isEmpty = value.length === 0;

        return (
            <div
                ref={divRef}
                role="textbox"
                aria-multiline="true"
                contentEditable={!disabled}
                suppressContentEditableWarning
                data-placeholder={placeholder}
                className={
                    `${className ?? ''} ${isEmpty ? 'is-empty' : ''}`.trim()
                }
                onInput={emitChange}
                onKeyDown={(e) => {
                    // Backspace onto a chip decomposes it to an editable `@name`
                    // query (and reopens search) instead of deleting it whole.
                    if (
                        e.key === 'Backspace' &&
                        !e.nativeEvent.isComposing &&
                        divRef.current
                    ) {
                        const chip = chipBeforeCollapsedCaret(divRef.current);
                        if (chip) {
                            e.preventDefault();
                            decomposeChip(chip);
                            return;
                        }
                    }
                    onKeyDown?.(e);
                }}
                onKeyUp={() => onQueryChange?.(divRef.current ? readActiveQuery(divRef.current) : null)}
                onClick={() => onQueryChange?.(divRef.current ? readActiveQuery(divRef.current) : null)}
                onPaste={(e) => {
                    // Let the parent handle files first; if it doesn't consume,
                    // fall back to inserting plain text (never rich HTML).
                    onPaste?.(e);
                    if (e.defaultPrevented) return;
                    const text = e.clipboardData?.getData('text/plain');
                    if (text != null) {
                        e.preventDefault();
                        document.execCommand('insertText', false, text);
                    }
                }}
                onCompositionStart={() => {
                    isComposingRef.current = true;
                    onCompositionStart?.();
                }}
                onCompositionEnd={() => {
                    isComposingRef.current = false;
                    onCompositionEnd?.();
                    // Composition committed characters via the DOM; resync value.
                    emitChange();
                }}
            />
        );
    },
);

MentionTextArea.displayName = 'MentionTextArea';
