/**
 * Extra file-tree actions that depend on where the console is running.
 *
 * The desktop shell talks to a backend on loopback and can reveal the file in
 * the local file manager. A browser cannot do that for a server-side sandbox,
 * so Download is how that copy is saved. There is no separate "remote sandbox"
 * flag on the desktop shell; the shell check is the reliable distinction.
 */
export function fileContextExtras(input: {
  isDirectory: boolean;
  /** True when the UI is the browser console, not the Tauri shell. */
  web: boolean;
  /** False for the read-only mounts root. */
  canMutate: boolean;
}): { download: boolean; upload: boolean } {
  return {
    download: input.web && !input.isDirectory,
    upload: input.canMutate && input.isDirectory,
  };
}
