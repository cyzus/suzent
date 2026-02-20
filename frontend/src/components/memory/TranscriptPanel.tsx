/**
 * Transcript Panel Component
 * Displays session transcripts with role-based styling
 */

import { useState, useEffect, Fragment } from 'react';
import { memoryApi } from '../../lib/memoryApi';
import { useChatStore } from '../../hooks/useChatStore';
import type { TranscriptEntry } from '../../types/memory';

function formatTimestamp(ts: string): string {
  try {
    const date = new Date(ts);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return ts;
  }
}

function formatDate(ts: string): string {
  try {
    const date = new Date(ts);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return '';
  }
}

function getRoleStyle(role: string): string {
  switch (role.toLowerCase()) {
    case 'user':
      return 'border-l-4 border-l-brutal-black bg-neutral-50';
    case 'assistant':
      return 'border-l-4 border-l-neutral-400 bg-white';
    case 'system':
      return 'border-l-4 border-l-neutral-200 bg-neutral-100';
    default:
      return 'border-l-4 border-l-neutral-300 bg-white';
  }
}

const MAX_CONTENT_PREVIEW = 500;

function formatEntryContent(content: string): string {
  if (typeof content !== 'string') {
    return JSON.stringify(content, null, 2);
  }
  if (content.length > MAX_CONTENT_PREVIEW) {
    return content.slice(0, MAX_CONTENT_PREVIEW) + '...';
  }
  return content;
}

export const TranscriptPanel: React.FC = () => {
  const { currentChatId, chats } = useChatStore();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastN, setLastN] = useState<number | undefined>(undefined);
  const [lastNInput, setLastNInput] = useState('');

  // Auto-select current chat
  useEffect(() => {
    if (currentChatId && !selectedSessionId) {
      setSelectedSessionId(currentChatId);
    }
  }, [currentChatId, selectedSessionId]);

  const loadTranscript = async (sessionId: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await memoryApi.getSessionTranscript(sessionId, lastN);
      setEntries(result.entries);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load transcript';
      if (msg.includes('404') || msg.includes('Not Found')) {
        setEntries([]);
        setError(null);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  // Load transcript when session or filter changes
  useEffect(() => {
    if (selectedSessionId) {
      loadTranscript(selectedSessionId);
    }
  }, [selectedSessionId, lastN]);

  const handleLastNSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const val = lastNInput.trim();
    if (val === '') {
      setLastN(undefined);
    } else {
      const n = parseInt(val, 10);
      if (!isNaN(n) && n > 0) {
        setLastN(n);
      }
    }
  };

  const sessionOptions = chats?.map((c) => ({
    id: c.id,
    label: c.title || c.id.slice(0, 12) + '...',
  })) ?? [];

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="bg-brutal-black text-white p-3 border-3 border-brutal-black">
        <h3 className="font-brutal text-xl uppercase tracking-tight">Session Transcripts</h3>
        <p className="text-xs text-neutral-300 font-mono">JSONL_CONVERSATION_LOG</p>
      </div>

      {/* Session selector + filter */}
      <div className="border-3 border-brutal-black bg-white shadow-brutal p-4 space-y-3">
        <div className="flex flex-col md:flex-row gap-3">
          {/* Session selector */}
          <div className="flex-1">
            <label className="block text-xs font-bold uppercase text-neutral-600 mb-1">
              Session
            </label>
            <select
              value={selectedSessionId || ''}
              onChange={(e) => setSelectedSessionId(e.target.value || null)}
              className="w-full px-3 py-2 border-3 border-brutal-black bg-white text-sm font-mono focus:outline-none focus:ring-4 focus:ring-brutal-black"
            >
              <option value="">Select a session...</option>
              {sessionOptions.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Last N filter */}
          <div className="w-full md:w-auto">
            <label className="block text-xs font-bold uppercase text-neutral-600 mb-1">
              Last N Entries
            </label>
            <form onSubmit={handleLastNSubmit} className="flex gap-2">
              <input
                type="number"
                min="1"
                value={lastNInput}
                onChange={(e) => setLastNInput(e.target.value)}
                placeholder="All"
                className="flex-1 px-3 py-2 border-3 border-brutal-black bg-white text-sm font-mono focus:outline-none focus:ring-4 focus:ring-brutal-black"
              />
              <button
                type="submit"
                className="px-3 py-2 border-3 border-brutal-black bg-brutal-black text-white font-bold text-xs uppercase hover:bg-neutral-800 transition-colors"
              >
                Go
              </button>
            </form>
          </div>
        </div>

        {/* Refresh */}
        {selectedSessionId && (
          <div className="flex items-center justify-between text-xs text-neutral-600">
            <span>
              {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
              {lastN !== undefined && ` (last ${lastN})`}
            </span>
            <button
              onClick={() => loadTranscript(selectedSessionId)}
              className="px-3 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 font-bold text-xs uppercase shadow-[2px_2px_0_0_#000] brutal-btn transition-all"
            >
              Refresh
            </button>
          </div>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="border-3 border-brutal-black bg-white p-8 text-center">
          <div className="w-4 h-4 border-3 border-brutal-black border-t-transparent animate-spin rounded-full mx-auto mb-2"></div>
          <p className="text-sm font-bold uppercase">Loading transcript...</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="border-3 border-brutal-black bg-white p-6">
          <p className="text-sm text-brutal-black font-mono">{error}</p>
        </div>
      )}

      {/* No session selected */}
      {!selectedSessionId && !loading && (
        <div className="border-3 border-brutal-black bg-white p-12 text-center">
          <h4 className="font-brutal text-2xl uppercase mb-2">Select a Session</h4>
          <p className="text-neutral-600 text-sm max-w-md mx-auto">
            Choose a session from the dropdown above to view its conversation transcript.
          </p>
        </div>
      )}

      {/* Empty state */}
      {selectedSessionId && !loading && !error && entries.length === 0 && (
        <div className="border-3 border-brutal-black bg-white p-12 text-center">
          <h4 className="font-brutal text-2xl uppercase mb-2">No Transcript Data</h4>
          <p className="text-neutral-600 text-sm max-w-md mx-auto">
            This session does not have a transcript yet. Transcripts are created when JSONL transcript logging is enabled.
          </p>
        </div>
      )}

      {/* Transcript entries */}
      {!loading && entries.length > 0 && (
        <div className="space-y-2">
          {entries.map((entry, index) => {
            const showDate = index === 0 || formatDate(entry.ts) !== formatDate(entries[index - 1].ts);

            return (
              <Fragment key={index}>
                {showDate && (
                  <div className="flex items-center gap-3 py-2">
                    <div className="flex-1 h-0.5 bg-neutral-200"></div>
                    <span className="text-xs font-bold uppercase text-neutral-500 px-2">
                      {formatDate(entry.ts)}
                    </span>
                    <div className="flex-1 h-0.5 bg-neutral-200"></div>
                  </div>
                )}
                <div className={`border-3 border-brutal-black p-4 ${getRoleStyle(entry.role)}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold uppercase tracking-wider px-2 py-0.5 border border-brutal-black bg-white text-brutal-black">
                      {entry.role.toUpperCase()}
                    </span>
                    <span className="text-xs font-mono text-neutral-500">
                      {formatTimestamp(entry.ts)}
                    </span>
                  </div>
                  <p className="text-sm font-mono leading-relaxed text-brutal-black whitespace-pre-wrap break-words">
                    {formatEntryContent(entry.content)}
                  </p>
                  {entry.actions && entry.actions.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-neutral-200">
                      <span className="text-[10px] font-bold uppercase text-neutral-500">
                        {entry.actions.length} action{entry.actions.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                  )}
                </div>
              </Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
};
