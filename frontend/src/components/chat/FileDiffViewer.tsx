import React, { useMemo } from 'react';
import { Editor, DiffEditor } from '@monaco-editor/react';
import { useTheme } from '../../hooks/useTheme';

interface FileDiffViewerProps {
  toolName: string;
  parsedArgs: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
}

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

export const FileDiffViewer: React.FC<FileDiffViewerProps> = ({ toolName, parsedArgs, metadata }) => {
  const { theme } = useTheme();
  const filePath = typeof parsedArgs?.file_path === 'string' ? parsedArgs.file_path : '';
  const language = getLanguageFromPath(filePath);
  
  const editorTheme = theme === 'dark' ? 'vs-dark' : 'light';

  const { isDiff, original, modified } = useMemo(() => {
    if (toolName === 'edit_file') {
      const oldContent = metadata?.old_content;
      const newContent = metadata?.new_content;

      if (typeof oldContent === 'string' && typeof newContent === 'string') {
        return {
          isDiff: true,
          original: oldContent,
          modified: newContent,
        };
      }

      return {
        isDiff: true,
        original: typeof parsedArgs?.old_string === 'string' ? parsedArgs.old_string : '',
        modified: typeof parsedArgs?.new_string === 'string' ? parsedArgs.new_string : '',
      };
    } else if (toolName === 'write_file') {
      const content = typeof parsedArgs?.content === 'string' ? parsedArgs.content : '';
      const oldContent = metadata?.old_content;
      
      if (typeof oldContent === 'string') {
        return {
          isDiff: true,
          original: oldContent,
          modified: content,
        };
      }
      return {
        isDiff: false,
        original: '',
        modified: content,
      };
    }
    return { isDiff: false, original: '', modified: '' };
  }, [toolName, parsedArgs, metadata]);

  // Options for Monaco Editor
  const options = {
    readOnly: true,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    fontSize: 12,
    wordWrap: 'on' as const,
    renderSideBySide: false, // Unified diff view is often better for inline chat
    automaticLayout: true,
    padding: { top: 8, bottom: 8 },
  };

  // Determine height based on content
  const lineCount = Math.max(
    original.split('\n').length,
    modified.split('\n').length
  );
  const height = Math.min(Math.max(lineCount * 19 + 16, 100), 500); // Between 100px and 500px

  return (
    <div className="w-full border-2 border-brutal-black dark:border-zinc-600 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] dark:shadow-none overflow-hidden bg-white dark:bg-[#1e1e1e] flex flex-col mt-2 transition-all">
      <div className="px-3 py-1.5 bg-neutral-100 dark:bg-zinc-800 border-b-2 border-brutal-black dark:border-zinc-600 flex justify-between items-center text-xs font-mono text-brutal-black dark:text-neutral-300 font-bold uppercase tracking-wider">
        <span>{filePath || 'Unknown file'}</span>
        <span className="opacity-75">{language}</span>
      </div>
      <div style={{ height: `${height}px` }} className="w-full">
        {isDiff ? (
          <DiffEditor
            original={original}
            modified={modified}
            language={language}
            theme={editorTheme}
            options={options}
            loading={<div className="p-4 text-xs text-neutral-500">Loading diff viewer...</div>}
          />
        ) : (
          <Editor
            value={modified}
            language={language}
            theme={editorTheme}
            options={options}
            loading={<div className="p-4 text-xs text-neutral-500">Loading code viewer...</div>}
          />
        )}
      </div>
    </div>
  );
};
