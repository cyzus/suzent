import React, { useEffect, type ReactNode } from 'react';
import { useLocation } from '@docusaurus/router';

const HOMEPAGE_PATHS = new Set(['/', '/zh-Hans', '/zh-Hans/']);

export default function Root({ children }: { children: ReactNode }): ReactNode {
  const { pathname } = useLocation();
  const isHome = HOMEPAGE_PATHS.has(pathname);

  useEffect(() => {
    const html = document.documentElement;
    if (isHome) {
      html.classList.add('homepage-mode');
    } else {
      html.classList.remove('homepage-mode');
    }
    return () => html.classList.remove('homepage-mode');
  }, [isHome]);

  return children;
}
