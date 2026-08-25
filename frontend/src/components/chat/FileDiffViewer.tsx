import React, { Suspense, lazy, useMemo } from 'react';
import type { BeforeMount } from '@monaco-editor/react';
import { SCHEME_COLORS, type Scheme, useTheme } from '../../hooks/useTheme';

// Monaco is bundled, not fetched from a CDN — see ./monacoEditors. Loading it
// lazily keeps it out of the initial bundle: the chunk is pulled the first time
// a file preview renders.
const Editor = lazy(() => import('./monacoEditors').then((m) => ({ default: m.Editor })));
const DiffEditor = lazy(() => import('./monacoEditors').then((m) => ({ default: m.DiffEditor })));

const EDITOR_OPTIONS = {
  readOnly: true,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  fontSize: 12,
  fontFamily: "Consolas, 'JetBrains Mono', 'Fira Code', 'SFMono-Regular', Menlo, Monaco, 'Liberation Mono', 'Ubuntu Mono', 'DejaVu Sans Mono', 'Segoe UI Symbol', 'Courier New', monospace",
  wordWrap: 'on' as const,
  renderSideBySide: false, // Unified diff is better for inline chat context
  automaticLayout: true,
  padding: { top: 8, bottom: 8 },
  // Disable features that touch the model asynchronously after layout/mouse
  // events. In this chat context editors mount/unmount rapidly, and these
  // features (sticky scroll, hover, code lens, overview ruler) race the model
  // teardown and throw uncaught errors like "Cannot read properties of
  // undefined (reading 'isVisible')", which abort the surrounding React render
  // and leave tool UI (e.g. an approval prompt) stuck.
  stickyScroll: { enabled: false },
  hover: { enabled: 'off' },
  codeLens: false,
  occurrencesHighlight: 'off' as const,
  selectionHighlight: false,
  overviewRulerLanes: 0,
  unicodeHighlight: {
    ambiguousCharacters: false,
    invisibleCharacters: false,
    nonBasicASCII: false,
  },
} as const;

const LOADING_FALLBACK = <div className="p-4 text-xs text-neutral-500">Loading viewer...</div>;

const THEME_PREFIX = 'suzent-file-viewer';
const REGISTERED_THEMES = new Set<string>();

const stripHash = (color: string): string => color.replace(/^#/, '');

const transparentize = (color: string, alphaHex: string): string => `${stripHash(color)}${alphaHex}`;

const getMonacoThemeName = (theme: 'light' | 'dark', scheme: Scheme): string => {
  return `${THEME_PREFIX}-${theme}-${scheme}`;
};

const makeBeforeMount = (): BeforeMount => {
  return (monaco) => {
    (['light', 'dark'] as const).forEach((themeNamePart) => {
      (['warm', 'cold', 'green'] as const).forEach((schemeNamePart) => {
        const themeName = getMonacoThemeName(themeNamePart, schemeNamePart);
        if (REGISTERED_THEMES.has(themeName)) return;

        const accent = SCHEME_COLORS[schemeNamePart][themeNamePart];
        const isDark = themeNamePart === 'dark';
        const background = isDark ? '#1e1e1e' : '#ffffff';
        const foreground = isDark ? '#e5e7eb' : '#111111';
        const muted = isDark ? '#a1a1aa' : '#6b7280';
        const gutter = isDark ? '#27272a' : '#f5f5f4';
        const line = isDark ? '#2f3138' : '#eeeeec';
        const selection = isDark ? transparentize(accent, '33') : transparentize(accent, '55');

        monaco.editor.defineTheme(themeName, {
          base: isDark ? 'vs-dark' : 'vs',
          inherit: true,
          rules: [
            { token: '', foreground: stripHash(foreground) },
            { token: 'comment', foreground: stripHash(muted), fontStyle: 'italic' },
            { token: 'keyword', foreground: stripHash(foreground), fontStyle: 'bold' },
            { token: 'number', foreground: isDark ? 'fbbf24' : '92400e' },
            { token: 'string', foreground: isDark ? '86efac' : '166534' },
            { token: 'type', foreground: stripHash(foreground), fontStyle: 'bold' },
            { token: 'function', foreground: stripHash(foreground) },
            { token: 'variable', foreground: stripHash(foreground) },
            { token: 'tag', foreground: stripHash(foreground), fontStyle: 'bold' },
            { token: 'attribute.name', foreground: stripHash(muted) },
            { token: 'delimiter', foreground: stripHash(foreground) },
            { token: 'strong', foreground: stripHash(foreground), fontStyle: 'bold' },
            { token: 'emphasis', foreground: stripHash(foreground), fontStyle: 'italic' },
            { token: 'markup.heading', foreground: stripHash(accent), fontStyle: 'bold' },
            { token: 'markup.quote', foreground: stripHash(muted) },
            { token: 'markup.list', foreground: stripHash(accent) },
            { token: 'markup.inline.raw', foreground: stripHash(foreground) },
          ],
          colors: {
            'editor.background': background,
            'editor.foreground': foreground,
            'editor.lineHighlightBackground': isDark ? '#ffffff08' : '#00000005',
            'editor.selectionBackground': `#${selection}`,
            'editor.inactiveSelectionBackground': isDark ? '#ffffff14' : '#00000012',
            'editorCursor.foreground': accent,
            'editorLineNumber.foreground': isDark ? '#71717a' : '#0e7490',
            'editorLineNumber.activeForeground': accent,
            'editorGutter.background': gutter,
            'editorIndentGuide.background1': line,
            'editorIndentGuide.activeBackground1': accent,
            'editorWhitespace.foreground': isDark ? '#ffffff1f' : '#0000001f',
            'scrollbar.shadow': '#00000000',
            'scrollbarSlider.background': isDark ? '#ffffff2b' : '#0000002b',
            'scrollbarSlider.hoverBackground': isDark ? '#ffffff45' : '#00000045',
            'scrollbarSlider.activeBackground': isDark ? '#ffffff66' : '#00000066',
            'diffEditor.insertedTextBackground': isDark ? '#22c55e26' : '#16a34a24',
            'diffEditor.removedTextBackground': isDark ? '#ef444426' : '#dc262624',
            'diffEditor.insertedLineBackground': isDark ? '#22c55e14' : '#16a34a12',
            'diffEditor.removedLineBackground': isDark ? '#ef444414' : '#dc262612',
            'diffEditor.diagonalFill': isDark ? '#71717a55' : '#a3a3a355',
          },
        });

        REGISTERED_THEMES.add(themeName);
      });
    });
  };
};

import type { ToolRendererProps } from './ToolCallBlock';
export type FileDiffViewerProps = ToolRendererProps;

type FileToolPreviewConfig = {
  modifiedArg: string;
  originalArg?: string;
  requireOriginalArg?: boolean;
  alwaysDiff?: boolean;
};

const FILE_TOOL_PREVIEW_CONFIG: Record<string, FileToolPreviewConfig | undefined> = {
  edit_file: {
    originalArg: 'old_string',
    modifiedArg: 'new_string',
    requireOriginalArg: true,
    alwaysDiff: true,
  },
  write_file: {
    modifiedArg: 'content',
  },
  read_file: {
    modifiedArg: '__read_file_output__',
  },
};

const getLanguageFromPath = (filePath: string): string => {
  const ext = filePath.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'py': return 'python';
    case 'ts':
    case 'tsx': return 'typescript';
    case 'js':
    case 'jsx': return 'javascript';
    case 'html': return 'html';
    case 'css': return 'css';
    case 'json': return 'json';
    case 'md': return 'markdown';
    case 'sh':
    case 'bash': return 'shell';
    case 'yml':
    case 'yaml': return 'yaml';
    case 'toml': return 'toml';
    case 'sql': return 'sql';
    case 'rs': return 'rust';
    case 'go': return 'go';
    case 'c': return 'c';
    case 'cpp': return 'cpp';
    default: return 'plaintext';
  }
};

const getStringProp = (source: Record<string, unknown> | null | undefined, key: string | undefined): string | undefined => {
  if (!source || !key) return undefined;
  const value = source[key];
  return typeof value === 'string' ? value : undefined;
};

const hasProp = (source: Record<string, unknown> | null | undefined, key: string | undefined): boolean => {
  return Boolean(source && key && Object.prototype.hasOwnProperty.call(source, key));
};

function countChangedLines(original: string, modified: string): { addedLines: number; removedLines: number } {
  const originalLines = original.split('\n');
  const modifiedLines = modified.split('\n');
  const lengths = Array.from({ length: originalLines.length + 1 }, () =>
    Array<number>(modifiedLines.length + 1).fill(0)
  );

  for (let i = originalLines.length - 1; i >= 0; i -= 1) {
    for (let j = modifiedLines.length - 1; j >= 0; j -= 1) {
      lengths[i][j] = originalLines[i] === modifiedLines[j]
        ? lengths[i + 1][j + 1] + 1
        : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }

  let i = 0;
  let j = 0;
  let addedLines = 0;
  let removedLines = 0;

  while (i < originalLines.length && j < modifiedLines.length) {
    if (originalLines[i] === modifiedLines[j]) {
      i += 1;
      j += 1;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      removedLines += 1;
      i += 1;
    } else {
      addedLines += 1;
      j += 1;
    }
  }

  removedLines += originalLines.length - i;
  addedLines += modifiedLines.length - j;
  return { addedLines, removedLines };
}

export interface FileContentDiffViewerProps {
  filePath: string;
  original: string;
  modified: string;
  isDiff?: boolean;
  addedLines?: number;
  removedLines?: number;
  embedded?: boolean;
  showFullPath?: boolean;
}

export const FileContentDiffViewer: React.FC<FileContentDiffViewerProps> = ({
  filePath,
  original,
  modified,
  isDiff = true,
  addedLines,
  removedLines,
  embedded = false,
  showFullPath = false,
}) => {
  const { theme, scheme } = useTheme();
  const editorTheme = getMonacoThemeName(theme, scheme);
  const beforeMount = useMemo(() => makeBeforeMount(), []);
  const language = getLanguageFromPath(filePath);
  const lineCount = Math.max(original.split('\n').length, modified.split('\n').length);
  const height = Math.min(Math.max(lineCount * 19 + 16, 110), embedded ? 360 : 500);
  const segments = filePath.split(/[/\\]/).filter(Boolean);
  const namePart = segments.pop() || filePath;
  const counts = useMemo(
    () => addedLines === undefined || removedLines === undefined
      ? countChangedLines(original, modified)
      : { addedLines, removedLines },
    [addedLines, modified, original, removedLines],
  );

  return (
    <div className={[
      'flex w-full flex-col overflow-hidden bg-white transition-all dark:bg-[#1e1e1e]',
      embedded
        ? 'border-0 shadow-none'
        : 'mt-2 border-2 border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] dark:border-zinc-600 dark:shadow-none',
    ].join(' ')}>
      <div className={[
        'flex items-center justify-between gap-3 px-3 py-1.5 font-mono text-xs font-bold tracking-wider text-brutal-black dark:text-neutral-300',
        embedded
          ? 'border-b border-neutral-300 bg-white/50 dark:border-zinc-700 dark:bg-white/[0.025]'
          : 'border-b-2 border-brutal-black bg-neutral-100 dark:border-zinc-600 dark:bg-zinc-800',
      ].join(' ')}>
        <span className="flex min-w-0 items-center gap-3">
          <span className={`${showFullPath ? '' : 'uppercase'} truncate`} title={filePath}>
            {showFullPath ? filePath : namePart}
          </span>
          {isDiff && (counts.addedLines > 0 || counts.removedLines > 0) && (
            <span className="flex items-center gap-1.5 opacity-90 text-[11px] shrink-0 font-bold">
              {counts.addedLines > 0 && <span className="text-green-600 dark:text-green-400">+{counts.addedLines}</span>}
              {counts.removedLines > 0 && <span className="text-red-600 dark:text-red-400">-{counts.removedLines}</span>}
            </span>
          )}
        </span>
        <span className="opacity-60 uppercase shrink-0">{language}</span>
      </div>
      <div style={{ height: `${height}px` }} className="w-full">
        <Suspense fallback={LOADING_FALLBACK}>
          {isDiff ? (
            <DiffEditor
              original={original}
              modified={modified}
              language={language}
              theme={editorTheme}
              options={EDITOR_OPTIONS}
              beforeMount={beforeMount}
              loading={LOADING_FALLBACK}
              // Chat blocks mount and unmount quickly. Keeping models alive avoids
              // a Monaco teardown race that can abort the surrounding React render.
              keepCurrentOriginalModel
              keepCurrentModifiedModel
            />
          ) : (
            <Editor
              value={modified}
              language={language}
              theme={editorTheme}
              options={EDITOR_OPTIONS}
              beforeMount={beforeMount}
              loading={LOADING_FALLBACK}
            />
          )}
        </Suspense>
      </div>
    </div>
  );
};

export const FileDiffViewer: React.FC<FileDiffViewerProps> = ({ toolName, parsedArgs, metadata, output }) => {
  const { filePath, isDiff, original, modified, canPreview, addedLines, removedLines } = useMemo(() => {
    const config = FILE_TOOL_PREVIEW_CONFIG[toolName];
    const rawPath = typeof metadata?.abs_path === 'string'
      ? metadata.abs_path
      : typeof parsedArgs?.file_path === 'string' ? parsedArgs.file_path
        : typeof parsedArgs?.path === 'string' ? parsedArgs.path
          : '';

    const filePath = rawPath;

    let isDiff = false;
    let original = '';
    let modified = '';
    let canPreview = false;
    let addedLines = 0;
    let removedLines = 0;

    if (config) {
      if (toolName === 'read_file' && output) {
        // Strip the "[Lines X-Y of Z]\n" header and tab-prefixed line numbers
        const bodyStart = output.indexOf('\n');
        const body = bodyStart >= 0 ? output.slice(bodyStart + 1) : output;
        modified = body.replace(/^\d+\t/gm, '');
        canPreview = modified.length > 0;
        isDiff = false;
      } else {
        const metadataOriginal = getStringProp(metadata, 'old_content');
        const metadataModified = getStringProp(metadata, 'new_content');
        const hasArgModified = hasProp(parsedArgs, config.modifiedArg);
        const hasArgOriginal = hasProp(parsedArgs, config.originalArg);

        original = metadataOriginal ?? getStringProp(parsedArgs, config.originalArg) ?? '';
        modified = metadataModified ?? getStringProp(parsedArgs, config.modifiedArg) ?? '';
        canPreview = metadataModified !== undefined || (
          hasArgModified && (!config.requireOriginalArg || hasArgOriginal)
        );
        isDiff = Boolean(config.alwaysDiff || metadataOriginal !== undefined || config.originalArg);
        if (metadataOriginal === undefined && !config.alwaysDiff) {
          isDiff = false;
        }

        if (isDiff) {
          ({ addedLines, removedLines } = countChangedLines(original, modified));
        }
      }
    }

    return { filePath, isDiff, original, modified, canPreview, addedLines, removedLines };
  }, [toolName, parsedArgs, metadata]);

  if (!canPreview) {
    return (
      <div className="max-h-[320px] overflow-y-auto scrollbar-thin w-full rounded-sm bg-neutral-50/70 dark:bg-zinc-800/40 px-2.5 py-2" style={{ overflowX: 'hidden' }}>
        <pre className="tool-call-pre font-mono text-[12px] leading-5 text-neutral-600 dark:text-neutral-300 w-full m-0">
          {output || '(no preview available)'}
        </pre>
      </div>
    );
  }

  return (
    <FileContentDiffViewer
      filePath={filePath}
      original={original}
      modified={modified}
      isDiff={isDiff}
      addedLines={addedLines}
      removedLines={removedLines}
    />
  );
};
