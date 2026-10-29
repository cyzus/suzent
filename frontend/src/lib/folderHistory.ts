export interface RecentFolder {
  path: string;
  timestamp: number;
}

const HISTORY_KEY = 'suzent_folder_history';
const MAX_HISTORY = 5;

/** Folders recently picked in any folder picker, newest first. */
export function readFolderHistory(): RecentFolder[] {
  try {
    const saved = localStorage.getItem(HISTORY_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch (e) {
    console.error('Failed to load folder history', e);
    return [];
  }
}

/** Puts `paths` at the front of the folder history and returns the new history. */
export function rememberFolders(paths: string[], history = readFolderHistory()): RecentFolder[] {
  const now = Date.now();
  const combined = [...paths.map((path) => ({ path, timestamp: now })), ...history];
  const trimmed = combined
    .filter((item, index, self) => index === self.findIndex((other) => other.path === item.path))
    .slice(0, MAX_HISTORY);
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed));
  } catch {
    // History is a convenience; a blocked localStorage just loses it.
  }
  return trimmed;
}
