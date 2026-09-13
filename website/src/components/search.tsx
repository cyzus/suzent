"use client";
import { useEffect, useState, useDeferredValue, useId } from "react";
import Link from "next/link";
import { useLocale, localePath } from "./locale";
import { messages } from "@/lib/messages";
interface Entry {
  url: string;
  title: string;
  text: string;
}
export function Search() {
  const locale = useLocale();
  const text = messages(locale);
  const id = useId();
  const [query, setQuery] = useState("");
  const deferred = useDeferredValue(query.trim().toLocaleLowerCase());
  const [index, setIndex] = useState<Entry[] | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setIndex(null);
    setError(false);
    fetch(localePath("/search-index.json", locale), {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("Search unavailable");
        return response.json();
      })
      .then(setIndex)
      .catch((error) => {
        if (error.name !== "AbortError") setError(true);
      });
    return () => controller.abort();
  }, [locale, attempt]);
  const terms = deferred.split(/\s+/).filter(Boolean);
  const results = !terms.length
    ? []
    : (index ?? [])
        .map((entry) => ({
          ...entry,
          score: terms.reduce(
            (score, term) =>
              score + (entry.title.toLocaleLowerCase().includes(term) ? 10 : 0),
            0,
          ),
        }))
        .filter((entry) =>
          terms.every((term) =>
            (entry.title + " " + entry.text).toLocaleLowerCase().includes(term),
          ),
        )
        .sort((a, b) => b.score - a.score)
        .slice(0, 8);
  return (
    <div className="doc-search">
      <label className="sr-only" htmlFor={id}>
        {text.search}
      </label>
      <input
        id={id}
        type="search"
        autoComplete="off"
        placeholder={text.searchPlaceholder}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setQuery("");
        }}
        aria-controls={id + "-results"}
        aria-expanded={!!deferred}
      />
      {deferred && (
        <div id={id + "-results"} className="search-results" aria-live="polite">
          {error ? (
            <>
              <p>{text.searchError}</p>
              <button onClick={() => setAttempt(attempt + 1)}>
                {text.retry}
              </button>
            </>
          ) : !index ? (
            <p>{text.searchLoading}</p>
          ) : results.length ? (
            results.map((entry) => {
              const start = Math.max(
                0,
                entry.text.toLocaleLowerCase().indexOf(terms[0]) - 35,
              );
              return (
                <Link
                  key={entry.url}
                  href={entry.url}
                  onClick={() => setQuery("")}
                >
                  <strong>{entry.title}</strong>
                  <span>
                    {start ? "…" : ""}
                    {entry.text.slice(start, start + 140)}…
                  </span>
                </Link>
              );
            })
          ) : (
            <p>{text.noResults}</p>
          )}
        </div>
      )}
    </div>
  );
}
