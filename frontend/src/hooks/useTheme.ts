import { useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';
export type Accent = 'yellow' | 'orange';

function getInitialTheme(): Theme {
  const stored = localStorage.getItem('suzent-theme') as Theme | null;
  if (stored === 'dark' || stored === 'light') return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getInitialAccent(): Accent {
  const stored = localStorage.getItem('suzent-accent') as Accent | null;
  if (stored === 'orange' || stored === 'yellow') return stored;
  return 'yellow';
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const [accent, setAccent] = useState<Accent>(getInitialAccent);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('suzent-theme', theme);
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    if (accent === 'orange') {
      root.classList.add('accent-orange');
    } else {
      root.classList.remove('accent-orange');
    }
    localStorage.setItem('suzent-accent', accent);
  }, [accent]);

  function toggleTheme() {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'));
  }

  function toggleAccent() {
    setAccent(a => (a === 'yellow' ? 'orange' : 'yellow'));
  }

  return { theme, toggleTheme, accent, toggleAccent };
}
