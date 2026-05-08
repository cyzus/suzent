import React, { useMemo } from 'react';
import { Editor, DiffEditor } from '@monaco-editor/react';
import { useTheme } from '../../hooks/useTheme';

const EDITOR_OPTIONS = {
  readOnly: true,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  fontSize: 12,
  wordWrap: 'on' as const,
  renderSideBySide: false, // Unified diff is better for inline chat context
  automaticLayout: true,
  padding: { top: 8, bottom: 8 },
} as const;

const LOADING_FALLBACK = <div className="p-4 text-xs text-neutral-500">Loading viewer...</div>;

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
  const { theme } = useTheme();
  const editorTheme = theme === 'dark' ? 'vs-dark' : 'light';

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
            loading={LOADING_FALLBACK}
          />
        ) : (
          <Editor
            value={modified}
            language={language}
            theme={editorTheme}
            options={EDITOR_OPTIONS}
            loading={LOADING_FALLBACK}
          />
        )}
      </div>
    </div>
  );
};
