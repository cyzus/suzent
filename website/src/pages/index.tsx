import { useState, useEffect, useRef, type ReactNode } from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import Head from '@docusaurus/Head';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import { useLocation } from '@docusaurus/router';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import Translate, { translate } from '@docusaurus/Translate';
import { useColorMode } from '@docusaurus/theme-common';

import { HeroArt } from '@site/src/components/HeroArt';
import { DotCube, type DotFieldPointer } from '@site/src/components/DotSphere';
import styles from './index.module.css';

const UNIX_CMD = `curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash`;
const WIN_CMD  = `irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex`;

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI'];

const FEATURE_CARDS = [
  {
    title: translate({ id: 'homepage.features.modelAgnostic.title', message: 'Model Agnostic' }),
    desc:  translate({ id: 'homepage.features.modelAgnostic.desc',  message: 'Use GPT, Claude, Gemini, and other providers through one local interface. Change models without rebuilding your workflow.' }),
  },
  {
    title: translate({ id: 'homepage.features.memory.title', message: 'Indelible Memory' }),
    desc:  translate({ id: 'homepage.features.memory.desc',  message: 'Markdown recall and semantic LanceDB search give the agent a durable record across sessions.' }),
  },
  {
    title: translate({ id: 'homepage.features.private.title', message: 'Sovereign Execution' }),
    desc:  translate({ id: 'homepage.features.private.desc',  message: 'Local-first architecture with sandboxed execution. Your files, memory, and runtime stay under your control.' }),
  },
  {
    title: translate({ id: 'homepage.features.automation.title', message: 'Scheduled Operations' }),
    desc:  translate({ id: 'homepage.features.automation.desc',  message: 'Run cron-like tasks, recurring checks, and long-lived monitors without bolting on another service.' }),
  },
  {
    title: translate({ id: 'homepage.features.skills.title', message: 'Skill Codex' }),
    desc:  translate({ id: 'homepage.features.skills.desc',  message: 'Package domain knowledge as Markdown skills. Add them locally when the agent needs a new discipline.' }),
  },
  {
    title: translate({ id: 'homepage.features.crossPlatform.title', message: 'Evolvable by Design' }),
    desc:  translate({ id: 'homepage.features.crossPlatform.desc',  message: 'Runs on Windows, macOS, and Linux. Extend the system through Nodes, skills, and companion devices over WebSocket.' }),
  },
];

// ─── Nav ─────────────────────────────────────────────────────────────────────

function SuzentLogo() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="0" y="0" width="24" height="24" rx="4" fill="var(--h-text)" />
      <rect x="5" y="8" width="5" height="5" rx="1.5" fill="var(--h-bg)" />
      <rect x="14" y="8" width="5" height="5" rx="1.5" fill="var(--h-bg)" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
      <circle cx="12" cy="12" r="4" />
      <line x1="12" y1="2" x2="12" y2="5" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="4.22" y1="4.22" x2="6.34" y2="6.34" />
      <line x1="17.66" y1="17.66" x2="19.78" y2="19.78" />
      <line x1="2" y1="12" x2="5" y2="12" />
      <line x1="19" y1="12" x2="22" y2="12" />
      <line x1="4.22" y1="19.78" x2="6.34" y2="17.66" />
      <line x1="17.66" y1="6.34" x2="19.78" y2="4.22" />
    </svg>
  );
}

function HomepageNav() {
  const { colorMode, setLightTheme, setDarkTheme } = useColorMode();
  const { i18n } = useDocusaurusContext();
  const { pathname } = useLocation();

  const otherLocale = i18n.locales.find(l => l !== i18n.currentLocale);
  const otherLabel  = otherLocale === 'zh-Hans' ? '中文' : 'EN';

  function switchLocaleHref(): string {
    if (!otherLocale) return '#';
    const stripped = pathname.replace(/^\/(zh-Hans)(\/|$)/, '/') || '/';
    return otherLocale === i18n.defaultLocale ? stripped : `/zh-Hans${stripped === '/' ? '/' : stripped}`;
  }

  return (
    <nav className={styles.homeNav} aria-label="Homepage navigation">
      <div className={styles.homeNavInner}>
        <Link to="/" className={styles.homeNavBrand}>
          <SuzentLogo />
          <span className={styles.homeNavTitle}>SUZENT</span>
        </Link>
        <div className={styles.homeNavLinks}>
          <Link to="/docs/getting-started/intro" className={styles.homeNavLink}>Docs</Link>
          <a href="https://github.com/cyzus/suzent" className={styles.homeNavLink} target="_blank" rel="noopener noreferrer">GitHub</a>
          {otherLocale && (
            <a href={switchLocaleHref()} className={styles.homeNavLink}>{otherLabel}</a>
          )}
          <button
            className={styles.themeToggleBtn}
            onClick={() => colorMode === 'dark' ? setLightTheme() : setDarkTheme()}
            aria-label="Toggle dark mode"
          >
            {colorMode === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>
    </nav>
  );
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button className={clsx(styles.copyBtn, copied && styles.copyBtnDone)} onClick={copy}>
      {copied ? '✓' : 'COPY'}
    </button>
  );
}

function ScrambleTitle({ text }: { text: string }) {
  const [displayText, setDisplayText] = useState(text);
  const intervalRef = useRef<number | null>(null);
  const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ◈⊕⊗◆▲✦—+*';

  const handleMouseEnter = () => {
    let frame = 0;
    const resolved = new Set<number>();
    if (intervalRef.current) window.clearInterval(intervalRef.current);

    intervalRef.current = window.setInterval(() => {
      if (frame > 10 && frame % 3 === 0) {
        const pool = text.split('').map((_, i) => i).filter(i => !resolved.has(i));
        if (pool.length) resolved.add(pool[Math.floor(Math.random() * pool.length)]);
      }
      if (resolved.size >= text.length) {
        setDisplayText(text);
        window.clearInterval(intervalRef.current!);
      } else {
        setDisplayText(text.split('').map((_, i) =>
          resolved.has(i) ? text[i] : CHARS[Math.floor(Math.random() * CHARS.length)]
        ).join(''));
      }
      frame++;
    }, 30);
  };

  return (
    <span className={styles.heroTitleInner} data-text={displayText} onMouseEnter={handleMouseEnter}>
      {displayText}
    </span>
  );
}

// ─── Hero ─────────────────────────────────────────────────────────────────────

function HomepageHeader() {
  const { siteConfig } = useDocusaurusContext();
  const [platform, setPlatform] = useState<'unix' | 'windows'>('unix');
  const [orbPointer, setOrbPointer] = useState<DotFieldPointer>({ x: 0, y: 0, active: false });
  const heroOrbRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (navigator.userAgent.includes('Windows')) setPlatform('windows');
  }, []);

  useEffect(() => {
    function updateOrbPointer(clientX: number, clientY: number, active: boolean) {
      if (!heroOrbRef.current) return;

      const rect = heroOrbRef.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const maxDistance = Math.max(rect.width, rect.height) * 0.95;
      const x = (clientX - centerX) / maxDistance;
      const y = (clientY - centerY) / maxDistance;

      setOrbPointer({
        x: Math.max(-1, Math.min(1, x)),
        y: Math.max(-1, Math.min(1, y)),
        active,
      });
    }

    function handlePointerMove(event: PointerEvent) {
      updateOrbPointer(event.clientX, event.clientY, true);
    }

    function handlePointerLeave(event: PointerEvent) {
      updateOrbPointer(event.clientX, event.clientY, false);
    }

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerleave', handlePointerLeave);

    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerleave', handlePointerLeave);
    };
  }, []);

  const installCmd = platform === 'windows' ? WIN_CMD : UNIX_CMD;

  return (
    <header className={styles.heroBanner}>

      {/* Above fold — title + orb fills the full viewport */}
      <div className={styles.heroInner}>
        <div className={styles.heroTitleArea}>
          <div className={styles.heroTitleBox}>
            <ScrambleTitle text={siteConfig.title} />
          </div>
          <p className={styles.heroSubtitle}>
            <Translate id="homepage.hero.kicker">SOVEREIGN LOCAL INTELLIGENCE</Translate>
          </p>
        </div>

        <div className={styles.heroOrb} ref={heroOrbRef}>
          <DotCube pointer={orbPointer} />
          <HeroArt pointer={orbPointer} />
        </div>

        <p className={styles.heroTagline}>
          <Translate id="homepage.hero.subtitle">Local. · Persistent. · Sovereign.</Translate>
        </p>
      </div>

      {/* Below fold — install + CTA revealed on scroll */}
      <div className={styles.heroAction}>
        <div className={styles.heroInstall}>
          <div className={styles.platformTabs}>
            <button
              className={clsx(styles.platformTab, platform === 'unix' && styles.platformTabActive)}
              onClick={() => setPlatform('unix')}
            >Mac / Linux</button>
            <button
              className={clsx(styles.platformTab, platform === 'windows' && styles.platformTabActive)}
              onClick={() => setPlatform('windows')}
            >Windows</button>
          </div>
          <div className={styles.cmdRow}>
            <pre className={styles.cmdText}>{installCmd}</pre>
            <CopyButton text={installCmd} />
          </div>
          <div className={styles.installDivider}>
            <span className={styles.installDividerLine} />
            <span className={styles.installDividerLabel}>then run</span>
            <span className={styles.installDividerLine} />
          </div>
          <div className={styles.cmdRow}>
            <pre className={styles.cmdText}>suzent start</pre>
            <CopyButton text="suzent start" />
          </div>
        </div>

        <div className={styles.heroCta}>
          <Link className={styles.heroCtaBtn} to="/docs/getting-started/quickstart">
            <Translate id="homepage.hero.cta.primary">Open the Guide</Translate>
          </Link>
        </div>
      </div>

    </header>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Home(): ReactNode {
  return (
    <Layout
      title={translate({ id: 'homepage.meta.title', message: 'Sovereign local intelligence' })}
      description={translate({ id: 'homepage.meta.description', message: 'A model-agnostic, local-first agent with durable memory, scheduled operations, and sovereign control over your data.' })}
    >
      <Head>
        <style>{`.navbar,.navbar--fixed-top{display:none!important}`}</style>
      </Head>
      <HomepageNav />
      <HomepageHeader />

      <main>
        <section className={styles.featuresSection}>
          <div className="container">
            <div className={styles.featuresHeader}>
              <span className={styles.featuresRuleLine} />
              <span className={styles.featuresRuleLabel}>LOCAL CAPABILITIES</span>
              <span className={styles.featuresRuleLine} />
            </div>
            <div className={styles.grid}>
              {FEATURE_CARDS.map(({ title, desc }, i) => (
                <article key={title} className={styles.featureCard}>
                  <div className={styles.featureCardNum}>{ROMAN[i]}</div>
                  <Heading as="h3" className={styles.featureTitle}>{title}</Heading>
                  <p className={styles.featureDesc}>{desc}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
