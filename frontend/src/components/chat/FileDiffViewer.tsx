import React, { useMemo } from 'react';
import { Editor, DiffEditor, type BeforeMount } from '@monaco-editor/react';
import { SCHEME_COLORS, type Scheme, useTheme } from '../../hooks/useTheme';

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

const makeBeforeMount = (theme: 'light' | 'dark', scheme: Scheme): BeforeMount => {
  const themeName = getMonacoThemeName(theme, scheme);

  return (monaco) => {
    if (REGISTERED_THEMES.has(themeName)) return;

    const accent = SCHEME_COLORS[scheme][theme];
    const isDark = theme === 'dark';
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

export const FileDiffViewer: React.FC<FileDiffViewerProps> = ({ toolName, parsedArgs, metadata, output }) => {
  const { theme, scheme } = useTheme();
  const editorTheme = getMonacoThemeName(theme, scheme);
  const beforeMount = useMemo(() => makeBeforeMount(theme, scheme), [theme, scheme]);

  const { filePath, dirPart, namePart, language, isDiff, original, modified, height, canPreview } = useMemo(() => {
    const config = FILE_TOOL_PREVIEW_CONFIG[toolName];
    const filePath = typeof metadata?.abs_path === 'string'
      ? metadata.abs_path
      : typeof parsedArgs?.file_path === 'string' ? parsedArgs.file_path
        : typeof parsedArgs?.path === 'string' ? parsedArgs.path
          : '';
    const lastSep = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'));
    const dirPart = lastSep >= 0 ? filePath.slice(0, lastSep + 1) : '';
    const namePart = lastSep >= 0 ? filePath.slice(lastSep + 1) : filePath;
    const language = getLanguageFromPath(filePath);

    let isDiff = false;
    let original = '';
    let modified = '';
    let canPreview = false;

    if (config) {
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
    }

    const lineCount = Math.max(original.split('\n').length, modified.split('\n').length);
    const height = Math.min(Math.max(lineCount * 19 + 16, 100), 500);

    return { filePath, dirPart, namePart, language, isDiff, original, modified, height, canPreview };
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
    <div className="w-full border-2 border-brutal-black dark:border-zinc-600 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] dark:shadow-none overflow-hidden bg-white dark:bg-[#1e1e1e] flex flex-col mt-2 transition-all">
      <div className="px-3 py-1.5 bg-neutral-100 dark:bg-zinc-800 border-b-2 border-brutal-black dark:border-zinc-600 flex justify-between items-center text-xs font-mono text-brutal-black dark:text-neutral-300 font-bold uppercase tracking-wider">
        {filePath ? (
          <span>
            <span className="opacity-50 font-normal">{dirPart}</span>
            <span>{namePart}</span>
          </span>
        ) : (
          <span>Unknown file</span>
        )}
        <span className="opacity-75">{language}</span>
      </div>
      <div style={{ height: `${height}px` }} className="w-full">
        {isDiff ? (
          <DiffEditor
            original={original}
            modified={modified}
            language={language}
            theme={editorTheme}
            options={EDITOR_OPTIONS}
            beforeMount={beforeMount}
            loading={LOADING_FALLBACK}
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
      </div>
    </div>
  );
};
