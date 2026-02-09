/**
 * Memory File Panel Component
 * Displays the curated MEMORY.md content in a read-only view
 */

import { useState, useEffect } from 'react';
import { memoryApi } from '../../lib/memoryApi';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const MemoryFilePanel: React.FC = () => {
  const [content, setContent] = useState<string | null>(null);
  const [sizeBytes, setSizeBytes] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reindexing, setReindexing] = useState(false);
  const [reindexResult, setReindexResult] = useState<string | null>(null);

  const loadMemoryFile = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await memoryApi.getMemoryFile();
      setContent(result.content);
      setSizeBytes(result.size_bytes);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load MEMORY.md';
      // 404 means file doesn't exist yet - not an error
      if (msg.includes('404') || msg.includes('Not Found')) {
        setContent(null);
        setError(null);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMemoryFile();
  }, []);

  const handleReindex = async () => {
    setReindexing(true);
    setReindexResult(null);
    try {
      const result = await memoryApi.reindexMemories(false);
      if (result.success) {
        setReindexResult('Reindex completed successfully');
        await loadMemoryFile();
      } else {
        setReindexResult('Reindex failed');
      }
    } catch (err) {
      setReindexResult(err instanceof Error ? err.message : 'Reindex failed');
    } finally {
      setReindexing(false);
    }
  };

  if (loading) {
    return (
      <div className="border-3 border-brutal-black bg-white p-6 shadow-brutal">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-3 border-brutal-black border-t-transparent animate-spin rounded-full"></div>
          <span className="font-bold uppercase text-sm">Loading MEMORY.md...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-3 border-brutal-black bg-white p-6 shadow-brutal">
        <h3 className="font-brutal text-xl text-brutal-black mb-2 uppercase">Error</h3>
        <p className="text-sm text-brutal-black font-mono mb-4">{error}</p>
        <button
          onClick={loadMemoryFile}
          className="px-6 py-2 border-3 border-brutal-black bg-white hover:bg-neutral-100 font-bold uppercase shadow-[2px_2px_0_0_#000] brutal-btn transition-all"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between bg-brutal-black text-white p-3 border-3 border-brutal-black">
        <div>
          <h3 className="font-brutal text-xl uppercase tracking-tight">MEMORY.md</h3>
          <p className="text-xs text-neutral-300 font-mono">
            {content ? `${formatSize(sizeBytes)} • CURATED_LONG_TERM` : 'NOT_CREATED_YET'}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadMemoryFile}
            className="px-3 py-1 border-2 border-white bg-brutal-black hover:bg-white hover:text-brutal-black font-bold text-xs uppercase transition-all"
          >
            Refresh
          </button>
          <button
            onClick={handleReindex}
            disabled={reindexing}
            className="px-3 py-1 border-2 border-white bg-brutal-black hover:bg-white hover:text-brutal-black font-bold text-xs uppercase transition-all disabled:opacity-50"
          >
            {reindexing ? 'Reindexing...' : 'Reindex'}
          </button>
        </div>
      </div>

      {/* Reindex status */}
      {reindexResult && (
        <div className="border-3 border-brutal-black bg-white p-3 text-sm font-mono">
          {reindexResult}
        </div>
      )}

      {/* Content */}
      {content ? (
        <div className="border-3 border-brutal-black bg-white shadow-brutal">
          <pre className="whitespace-pre-wrap font-mono text-sm p-6 max-h-[70vh] overflow-y-auto scrollbar-thin leading-relaxed text-brutal-black">
            {content}
          </pre>
        </div>
      ) : (
        <div className="border-3 border-brutal-black bg-white p-12 text-center shadow-brutal">
          <h4 className="font-brutal text-2xl uppercase mb-2">No MEMORY.md Yet</h4>
          <p className="text-neutral-600 text-sm max-w-md mx-auto">
            The curated long-term memory file will be created automatically as the agent processes conversations and extracts key facts.
          </p>
        </div>
      )}
    </div>
  );
};
