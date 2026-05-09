import React, { useState, useRef, useEffect } from 'react';
import { useLocation } from '@docusaurus/router';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import clsx from 'clsx';

const LOCALE_LABEL: Record<string, string> = {
  en: 'EN',
  'zh-Hans': '中文',
};

function localeHref(locale: string, defaultLocale: string, pathname: string): string {
  const stripped = pathname.replace(/^\/(zh-Hans)(\/|$)/, '/') || '/';
  return locale === defaultLocale ? stripped : `/zh-Hans${stripped === '/' ? '/' : stripped}`;
}

export default function LocaleDropdownNavbarItem({
  mobile,
}: {
  mobile?: boolean;
  // Accept (and ignore) any extra props Docusaurus passes
  [key: string]: unknown;
}) {
  const { i18n } = useDocusaurusContext();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const others = i18n.locales.filter(l => l !== i18n.currentLocale);
  const currentLabel = LOCALE_LABEL[i18n.currentLocale] ?? i18n.currentLocale.toUpperCase();

  if (mobile) {
    return (
      <>
        {others.map(locale => (
          <a
            key={locale}
            href={localeHref(locale, i18n.defaultLocale, pathname)}
            className="menu__link"
          >
            {LOCALE_LABEL[locale] ?? locale}
          </a>
        ))}
      </>
    );
  }

  return (
    <div ref={ref} className="navbar__item dropdown dropdown--hoverable" style={{ position: 'relative' }}>
      <button
        className="navbar__link"
        onClick={() => setOpen(v => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 0.5rem' }}
      >
        {currentLabel}
      </button>
      {open && others.length > 0 && (
        <ul className={clsx('dropdown__menu')} style={{ display: 'block', right: 0, left: 'auto' }}>
          {others.map(locale => (
            <li key={locale}>
              <a
                href={localeHref(locale, i18n.defaultLocale, pathname)}
                className="dropdown__link"
                onClick={() => setOpen(false)}
              >
                {LOCALE_LABEL[locale] ?? locale}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
