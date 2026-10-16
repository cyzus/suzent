/**
 * Task-completion notification preferences.
 *
 * These are device-local UI choices (like theme and language), not backend
 * state: whether to pop a notification and what sound to play are decisions
 * about this machine, so they live in localStorage alongside `suzent-theme`.
 */
import { useEffect, useState } from 'react';

/** When a finished task may raise a notification. */
export type NotificationWhen = 'always' | 'background' | 'never';

/** The bundled notification sounds. `none` keeps things silent. */
export type NotificationSound = 'none' | 'chime' | 'ping' | 'bell' | 'resonance' | 'success';

export interface NotificationPreferences {
  when: NotificationWhen;
  sound: NotificationSound;
}

export const NOTIFICATION_WHEN_OPTIONS: readonly NotificationWhen[] = [
  'always',
  'background',
  'never',
];

export const NOTIFICATION_SOUND_OPTIONS: readonly NotificationSound[] = [
  'none',
  'chime',
  'ping',
  'bell',
  'resonance',
  'success',
];

/** Matches the pre-feature behaviour: always notify, with a gentle chime. */
export const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  when: 'always',
  sound: 'chime',
};

const STORAGE_KEY = 'suzent-notification-preferences';

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function emitChange(): void {
  for (const listener of listeners) listener();
}

function isWhen(value: unknown): value is NotificationWhen {
  return value === 'always' || value === 'background' || value === 'never';
}

function isSound(value: unknown): value is NotificationSound {
  return (
    typeof value === 'string' &&
    (NOTIFICATION_SOUND_OPTIONS as readonly string[]).includes(value)
  );
}

/** Read the stored preferences, falling back to defaults on absence or corruption. */
export function readNotificationPreferences(): NotificationPreferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<NotificationPreferences>;
      return {
        when: isWhen(parsed.when) ? parsed.when : DEFAULT_NOTIFICATION_PREFERENCES.when,
        sound: isSound(parsed.sound) ? parsed.sound : DEFAULT_NOTIFICATION_PREFERENCES.sound,
      };
    }
  } catch {
    /* storage blocked or malformed */
  }
  return { ...DEFAULT_NOTIFICATION_PREFERENCES };
}

export function writeNotificationPreferences(preferences: NotificationPreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    /* storage blocked */
  }
  emitChange();
}

/**
 * Whether a finished task should notify under the given policy. `background`
 * means only when the window is hidden, so a reply that finishes while the
 * user is already watching does not interrupt.
 */
export function shouldNotifyForCompletion(when: NotificationWhen): boolean {
  if (when === 'never') return false;
  if (when === 'background') {
    try {
      return typeof document !== 'undefined' && document.visibilityState === 'hidden';
    } catch {
      return false;
    }
  }
  return true;
}

export interface NotificationPreferencesApi {
  preferences: NotificationPreferences;
  setWhen: (when: NotificationWhen) => void;
  setSound: (sound: NotificationSound) => void;
}

/** Reactive preferences for the settings panel; consumers of the actual
 * completion events read the value directly instead. */
export function useNotificationPreferences(): NotificationPreferencesApi {
  const [preferences, setPreferences] = useState<NotificationPreferences>(
    readNotificationPreferences
  );

  useEffect(
    () => subscribe(() => setPreferences(readNotificationPreferences())),
    []
  );

  return {
    preferences,
    setWhen: (when) => writeNotificationPreferences({ ...preferences, when }),
    setSound: (sound) => writeNotificationPreferences({ ...preferences, sound }),
  };
}
