import React, { useEffect, useRef, useState } from 'react';
import { useTheme } from '../hooks/useTheme';

let idCounter = 0;

interface MermaidDiagramProps {
  code: string;
}

// Renders Mermaid source into an inline SVG. Mermaid is imported lazily so the
// (large) library is only pulled in when a diagram is actually shown.
export const MermaidDiagram: React.FC<MermaidDiagramProps> = ({ code }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    let cancelled = false;

    const render = async () => {
      const trimmed = code.trim();
      if (!trimmed) {
        setError(null);
        if (containerRef.current) containerRef.current.innerHTML = '';
        return;
      }

      const id = `mermaid-${idCounter++}`;
      try {
        const mermaid = (await import('mermaid')).default;
        // initialize() is idempotent; re-running it picks up theme changes. The
        // built-in 'dark'/'default' themes follow the app's light/dark mode so a
        // diagram never renders light on a dark surface (or vice versa).
        // suppressErrorRendering stops mermaid from injecting its own "bomb"
        // error SVG into document.body on a parse failure — we render our own
        // error UI instead.
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          suppressErrorRendering: true,
          theme: theme === 'dark' ? 'dark' : 'default',
        });

        // parse() with suppressErrors returns false (instead of throwing) on
        // invalid syntax, so we can detect the failure without hitting render()'s
        // DOM-injecting failure path. On failure, re-parse without suppression to
        // recover the detailed message (line number / expected tokens) for the UI.
        const parsed = await mermaid.parse(trimmed, { suppressErrors: true });
        if (cancelled) return;
        if (parsed === false) {
          let detail = 'Invalid Mermaid syntax.';
          try {
            await mermaid.parse(trimmed);
          } catch (parseErr) {
            detail = parseErr instanceof Error ? parseErr.message : String(parseErr);
          }
          if (cancelled) return;
          setError(detail);
          if (containerRef.current) containerRef.current.innerHTML = '';
          return;
        }

        const { svg } = await mermaid.render(id, trimmed);
        if (cancelled) return;
        setError(null);
        // Defensive: an empty/whitespace SVG would otherwise leave a blank box
        // with no diagram and no error. Treat it as a failure.
        if (!svg || !svg.trim()) {
          setError('Mermaid produced an empty diagram.');
          if (containerRef.current) containerRef.current.innerHTML = '';
          return;
        }
        if (containerRef.current) containerRef.current.innerHTML = svg;
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        if (containerRef.current) containerRef.current.innerHTML = '';
        // render() can leave a detached temp node attached to body on failure;
        // remove the stray element so it can't leak into the page. Only on the
        // error path — on success this id belongs to the SVG we just injected
        // into the container, and removing it would wipe the rendered diagram.
        document.querySelector(`body > #${id}`)?.remove();
        document.querySelector(`body > #d${id}`)?.remove();
      }
    };

    void render();
    return () => {
      cancelled = true;
    };
  }, [code, theme]);

  if (error) {
    return (
      <div className="my-3 border-2 border-brutal-black bg-white dark:bg-zinc-900">
        <div className="px-3 py-1.5 bg-brutal-black text-white font-black uppercase text-[10px]">
          Mermaid error
        </div>
        <pre className="px-3 py-2 text-[12px] text-red-600 dark:text-red-400 whitespace-pre-wrap font-mono m-0">
          {error}
        </pre>
        <pre className="px-3 py-2 text-[12px] text-brutal-black dark:text-neutral-200 whitespace-pre overflow-x-auto font-mono m-0 border-t-2 border-brutal-black">
          {code}
        </pre>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-3 flex justify-center overflow-x-auto border-2 border-brutal-black bg-white dark:bg-zinc-900 p-3"
    />
  );
};
