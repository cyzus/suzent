import React, { useRef, useState } from 'react';
import { triggerPeer } from '../../lib/api';
import { SettingsListAction } from './SettingsCard';

/**
 * Send a prompt to a Suzent peer's agent and watch its reply stream back.
 *
 * The counterpart to NodeInvokePanel: a node exposes named commands you pick
 * from a manifest, whereas a peer is a whole agent you hand a goal to. Both
 * live on the device row so "what can I do with this machine?" has one answer.
 */
export function PeerTriggerPanel({
  peerId,
  paused,
}: {
  peerId: string;
  paused: boolean;
}): React.ReactElement {
  const [prompt, setPrompt] = useState('');
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Accumulate outside state so each delta doesn't depend on a stale closure.
  const buffer = useRef('');

  const run = async () => {
    const text = prompt.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setReply('');
    buffer.current = '';
    try {
      await triggerPeer(peerId, text, (delta) => {
        buffer.current += delta;
        setReply(buffer.current);
      });
      if (!buffer.current) setReply('(the remote agent returned no output)');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (paused) {
    return (
      <p className="text-xs text-neutral-500">
        Triggering is paused for this device. Enable it above to send prompts.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="flex-1 min-w-[12rem] px-2 py-1 border-2 border-brutal-black bg-white dark:bg-zinc-900 text-sm"
          placeholder="Ask this device's agent to do something…"
          value={prompt}
          disabled={busy}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') run();
          }}
        />
        <SettingsListAction tone="blue" disabled={busy || !prompt.trim()} onClick={run}>
          {busy ? 'Running…' : 'Send'}
        </SettingsListAction>
      </div>

      {reply && (
        <pre className="text-[11px] whitespace-pre-wrap overflow-x-auto border-2 border-brutal-green bg-green-50 p-2 dark:bg-green-900/20">
          {reply}
        </pre>
      )}
      {error && (
        <pre className="text-[11px] whitespace-pre-wrap overflow-x-auto border-2 border-brutal-red bg-red-50 p-2 dark:bg-red-900/20">
          {error}
        </pre>
      )}
    </div>
  );
}
