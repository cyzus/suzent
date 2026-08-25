/**
 * Self-hosted Monaco.
 *
 * `@monaco-editor/react` otherwise fetches Monaco from a jsdelivr URL at runtime.
 * That script is blocked outright in the packaged app — the Tauri CSP declares no
 * `script-src`, so it falls back to `default-src 'self'` — and in dev it depends on
 * the CDN being reachable. The wrapper only `console.error`s when the fetch fails
 * and never leaves its loading state, and the loader is a one-shot module
 * singleton, so a single failed fetch wedges every diff for the rest of the
 * session with no retry.
 *
 * Pointing the loader at a bundled instance makes `init()` resolve from local
 * state without touching the network, so dev and production behave identically
 * and both work offline.
 *
 * FileDiffViewer imports this module lazily to keep Monaco out of the initial
 * bundle. `loader.config` runs at module evaluation, which always precedes the
 * mount of any editor re-exported from here.
 */
import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
import EditorWorker from 'monaco-editor/editor/editor.worker?worker';
import CssWorker from 'monaco-editor/languages/features/css/css.worker?worker';
import HtmlWorker from 'monaco-editor/languages/features/html/html.worker?worker';
import JsonWorker from 'monaco-editor/languages/features/json/json.worker?worker';
import TsWorker from 'monaco-editor/languages/features/typescript/ts.worker?worker';

// Monaco resolves its workers through this global rather than through imports.
self.MonacoEnvironment = {
  getWorker(_workerId: string, label: string) {
    switch (label) {
      case 'json':
        return new JsonWorker();
      case 'css':
      case 'scss':
      case 'less':
        return new CssWorker();
      case 'html':
      case 'handlebars':
      case 'razor':
        return new HtmlWorker();
      case 'typescript':
      case 'javascript':
        return new TsWorker();
      default:
        // Also the worker the diff editor uses to compute diffs.
        return new EditorWorker();
    }
  },
};

loader.config({ monaco });

export { DiffEditor, Editor } from '@monaco-editor/react';
