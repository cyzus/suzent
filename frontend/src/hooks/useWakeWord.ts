import { useEffect, useRef, useState } from 'react';
import { desktopWindow, isDesktop, registerGlobalShortcut } from '../lib/desktop';
import { getApiBase } from '../lib/api';
import { WakeListener, type WakeErrorCode } from '../lib/voice/wakeListener';

/** The voice settings that decide how a call can be started hands-free. */
export interface VoiceTriggerSettings {
  wake_word: boolean;
  wake_phrases: string[];
  wake_sensitivity: number;
  voice_hotkey: string;
}

/** Fired by the settings page after a save, with the saved settings. */
export const VOICE_SETTINGS_EVENT = 'suzent:voice-settings';

/** The saved trigger settings, kept current when the settings page saves. */
export function useVoiceTriggerSettings(): VoiceTriggerSettings | null {
  const [settings, setSettings] = useState<VoiceTriggerSettings | null>(null);
  useEffect(() => {
    let cancelled = false;
    void fetch(`${getApiBase()}/config/voice`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data: VoiceTriggerSettings | null) => {
        if (!cancelled && data) setSettings(data);
      })
      .catch(() => undefined);
    const onSaved = (event: Event) =>
      setSettings((event as CustomEvent<VoiceTriggerSettings>).detail);
    window.addEventListener(VOICE_SETTINGS_EVENT, onSaved);
    return () => {
      cancelled = true;
      window.removeEventListener(VOICE_SETTINGS_EVENT, onSaved);
    };
  }, []);
  return settings;
}

export type WakeWordStatus = 'off' | 'starting' | 'listening' | 'error';

// After a dropped line, try again this long later (the backend may be restarting).
const RETRY_MS = 5000;

/**
 * Listen for the wake phrase while `enabled`, and call `onWake` on hearing it.
 * `settingsKey` restarts the listener when the phrases or sensitivity change.
 */
export function useWakeWord(
  enabled: boolean,
  settingsKey: string,
  onWake: (phrase: string) => void
): { status: WakeWordStatus; error: WakeErrorCode | null; detail: string } {
  const [status, setStatus] = useState<WakeWordStatus>('off');
  const [error, setError] = useState<{ code: WakeErrorCode; detail: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const onWakeRef = useRef(onWake);
  onWakeRef.current = onWake;

  useEffect(() => {
    if (!enabled) {
      setStatus('off');
      return;
    }
    setStatus('starting');
    let retry: ReturnType<typeof setTimeout> | undefined;
    const listener = new WakeListener({
      onListening: () => {
        setStatus('listening');
        setError(null);
      },
      onWake: (phrase) => onWakeRef.current(phrase),
      onError: (code, detail) => {
        setStatus('error');
        setError({ code, detail });
        // Settings problems wait for a settings change; a lost line retries.
        if (code === 'connection') retry = setTimeout(() => setAttempt((n) => n + 1), RETRY_MS);
      },
    });
    listener.start();
    return () => {
      if (retry) clearTimeout(retry);
      listener.stop();
    };
  }, [enabled, settingsKey, attempt]);

  return { status, error: error?.code ?? null, detail: error?.detail ?? '' };
}

/**
 * Register a desktop-wide shortcut (Tauri only) that brings Suzent forward
 * and calls `onPress`. An empty or invalid accelerator registers nothing.
 */
export function useVoiceHotkey(accelerator: string, onPress: () => void): void {
  const onPressRef = useRef(onPress);
  onPressRef.current = onPress;
  useEffect(() => {
    if (!accelerator || !isDesktop()) return;
    let disposed = false;
    let unregister: (() => void) | undefined;
    void (async () => {
      try {
        const stop = await registerGlobalShortcut(accelerator, () => {
          void desktopWindow.reveal().catch(() => undefined);
          onPressRef.current();
        });
        if (disposed) stop();
        else unregister = stop;
      } catch (err) {
        // Taken by another app, or not a valid accelerator.
        console.warn(`Voice shortcut ${accelerator} not registered:`, err);
      }
    })();
    return () => {
      disposed = true;
      unregister?.();
    };
  }, [accelerator]);
}
