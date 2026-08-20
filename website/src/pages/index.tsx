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
const WIN_CMD  = `powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"`;

const FEATURE_CARDS = [
  {
    arcana: translate({ id: 'homepage.features.modelAgnostic.arcana', message: 'I · SOVEREIGN MIND' }),
    sigil: '⊕',
    title: translate({ id: 'homepage.features.modelAgnostic.title', message: 'Choose the Model. Keep the Self.' }),
    desc:  translate({ id: 'homepage.features.modelAgnostic.desc',  message: 'Models are replaceable engines. Identity, memory, skills, and workspace remain yours when the provider changes.' }),
    formula: 'model ≠ identity',
  },
  {
    arcana: translate({ id: 'homepage.features.private.arcana', message: 'II · SOVEREIGN AUTHORITY' }),
    sigil: '□',
    title: translate({ id: 'homepage.features.private.title', message: 'Your Agent, Under Your Law' }),
    desc:  translate({ id: 'homepage.features.private.desc',  message: 'Permissions, scoped rules, sandbox boundaries, and an inspectable activity trail keep every action under your authority.' }),
    formula: 'action ⊆ your law',
  },
  {
    arcana: translate({ id: 'homepage.features.automation.arcana', message: 'III · SOVEREIGN VESSEL' }),
    sigil: '⌁',
    title: translate({ id: 'homepage.features.automation.title', message: 'Run Where You Hold the Keys' }),
    desc:  translate({ id: 'homepage.features.automation.desc',  message: 'Control the runtime, isolate project workspaces, mount your own folders, and extend the agent only to approved devices.' }),
    formula: 'runtime ∈ your domain',
  },
  {
    arcana: translate({ id: 'homepage.features.crossPlatform.arcana', message: 'IV · SOVEREIGN CONTINUITY' }),
    sigil: '△',
    title: translate({ id: 'homepage.features.crossPlatform.title', message: 'Outlive Any Platform' }),
    desc:  translate({ id: 'homepage.features.crossPlatform.desc',  message: 'Move memory, skills, and configuration while credentials stay local. Models and machines can change; your agent remains.' }),
    formula: 'self > platform',
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

/** Half sun / half moon — indicates "follow system preference". */
function AutoIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3v18" />
      <path d="M12 7a5 5 0 0 1 0 10" fill="currentColor" stroke="none" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

function HomepageNav() {
  const { colorModeChoice, setColorMode } = useColorMode();
  const { i18n } = useDocusaurusContext();
  const { pathname } = useLocation();

  const otherLocale = i18n.locales.find(l => l !== i18n.currentLocale);
  const otherLabel  = otherLocale === 'zh-Hans' ? '中文' : 'EN';

  function switchLocaleHref(): string {
    if (!otherLocale) return '#';
    const stripped = pathname.replace(/^\/(zh-Hans)(\/|$)/, '/') || '/';
    return otherLocale === i18n.defaultLocale ? stripped : `/zh-Hans${stripped === '/' ? '/' : stripped}`;
  }

  // Cycle: auto → light → dark → auto
  function cycleTheme() {
    if (colorModeChoice === null) setColorMode('light');
    else if (colorModeChoice === 'light') setColorMode('dark');
    else setColorMode(null);
  }

  const themeIcon =
    colorModeChoice === 'light' ? <SunIcon />
    : colorModeChoice === 'dark' ? <MoonIcon />
    : <AutoIcon />;
  const themeLabel =
    colorModeChoice === 'light' ? 'Light'
    : colorModeChoice === 'dark' ? 'Dark'
    : 'Auto';

  return (
    <nav className={styles.homeNav} aria-label="Homepage navigation">
      <div className={styles.homeNavInner}>
        <Link to="/" className={styles.homeNavBrand}>
          <SuzentLogo />
          <span className={styles.homeNavTitle}>SUZENT</span>
        </Link>
        <div className={styles.homeNavLinks}>
          <Link to="/docs/getting-started/intro" className={styles.homeNavLink}>Docs</Link>
          <Link to="/blog" className={styles.homeNavLink}>Blog</Link>
          <Link to="/sovereign" className={styles.homeNavLink}>
            <Translate id="homepage.nav.sovereign">Manifesto</Translate>
          </Link>
          <div className={styles.homeNavUtils}>
            <a href="https://github.com/cyzus/suzent" className={styles.homeNavIconLink} target="_blank" rel="noopener noreferrer" aria-label="GitHub">
              <GitHubIcon />
            </a>
            {otherLocale && (
              <a href={switchLocaleHref()} className={styles.homeNavIconLink} aria-label="Switch language">{otherLabel}</a>
            )}
            <button
              className={styles.homeNavIconLink}
              onClick={cycleTheme}
              aria-label={`Theme: ${themeLabel}`}
              title={themeLabel}
            >
              {themeIcon}
            </button>
          </div>
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
      {copied
        ? translate({ id: 'homepage.copy.sealed', message: 'SEALED' })
        : translate({ id: 'homepage.copy.copy', message: 'COPY' })}
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
          <Heading as="h1" className={styles.heroTitleBox}>
            <ScrambleTitle text={siteConfig.title} />
          </Heading>
          <p className={styles.heroSubtitle}>
            <Translate id="homepage.hero.kicker">THE SOVEREIGN AI AGENT</Translate>
          </p>
        </div>

        <div className={styles.heroOrb} ref={heroOrbRef}>
          <DotCube pointer={orbPointer} />
          <HeroArt pointer={orbPointer} />
        </div>

        <p className={styles.heroTagline}>
          <Translate id="homepage.hero.subtitle">Models are replaceable. Your agent remains.</Translate>
        </p>
      </div>

      {/* Below fold — install + CTA revealed on scroll */}
      <div className={styles.heroAction}>
        <div className={styles.heroInstall}>
          <div className={styles.installSystemBar}>
            <span><Translate id="homepage.install.status">RITUAL STATUS: LISTENING</Translate></span>
            <span><Translate id="homepage.install.saasJab">NO SUBSCRIPTION ALTAR REQUIRED</Translate></span>
          </div>
          <div className={styles.platformTabs}>
            <button
              className={clsx(styles.platformTab, platform === 'unix' && styles.platformTabActive)}
              onClick={() => setPlatform('unix')}
            ><Translate id="homepage.install.unix">Linux/Mac Rite</Translate></button>
            <button
              className={clsx(styles.platformTab, platform === 'windows' && styles.platformTabActive)}
              onClick={() => setPlatform('windows')}
            ><Translate id="homepage.install.windows">Windows Rite</Translate></button>
          </div>
          <div className={styles.cmdLabel}><Translate id="homepage.install.invocation">Invocation Script</Translate></div>
          <div className={styles.cmdRow}>
            <pre className={styles.cmdText}>{installCmd}</pre>
            <CopyButton text={installCmd} />
          </div>
          <div className={styles.installDivider}>
            <span className={styles.installDividerLine} />
            <span className={styles.installDividerLabel}><Translate id="homepage.install.thenRun">then run</Translate></span>
            <span className={styles.installDividerLine} />
          </div>
          <div className={styles.cmdLabel}><Translate id="homepage.install.vessel">Open Vessel</Translate></div>
          <div className={styles.cmdRow}>
            <pre className={styles.cmdText}>suzent start</pre>
            <CopyButton text="suzent start" />
          </div>
        </div>

        <div className={styles.heroCta}>
          <Link className={styles.heroCtaBtn} to="/docs/getting-started/quickstart">
            <Translate id="homepage.hero.cta.primary">Summon Suzent</Translate>
          </Link>
          <Link className={clsx(styles.heroCtaBtn, styles.heroCtaBtnSecondary)} to="/sovereign">
            <Translate id="homepage.hero.cta.sovereign">Read the Sovereignty Protocol</Translate>
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
      title={translate({ id: 'homepage.meta.title', message: 'The Sovereign AI Agent' })}
      description={translate({ id: 'homepage.meta.description', message: 'A sovereign AI agent whose identity, memory, skills, workspace, and runtime remain under your control—independent of any model or platform.' })}
    >
      <Head>
        <style>{`.navbar,.navbar--fixed-top,.footer{display:none!important}`}</style>
        <script type="application/ld+json">
          {JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'SoftwareApplication',
            name: 'Suzent',
            alternateName: 'The Sovereign AI Agent',
            description: 'A sovereign AI agent whose identity, memory, skills, workspace, and runtime remain under your control.',
            url: 'https://suzent.com/',
            applicationCategory: 'DeveloperApplication',
            operatingSystem: 'Windows, macOS, Linux',
            codeRepository: 'https://github.com/cyzus/suzent',
            downloadUrl: 'https://github.com/cyzus/suzent/releases',
            license: 'https://www.apache.org/licenses/LICENSE-2.0',
            featureList: [
              'Model-independent identity',
              'User-owned memory and skills',
              'Permissioned and sandboxed actions',
              'Portable agent state',
            ],
          })}
        </script>
      </Head>
      <HomepageNav />
      <HomepageHeader />

      <main>
        <section className={styles.featuresSection}>
          <div className="container">
            <div className={styles.featuresHeader}>
              <span className={styles.featuresRuleLine} />
              <span className={styles.featuresRuleLabel}><Translate id="homepage.features.label">WHAT MAKES AN AGENT SOVEREIGN?</Translate></span>
              <span className={styles.featuresRuleLine} />
            </div>
            <div className={styles.grid}>
              {FEATURE_CARDS.map(({ arcana, sigil, title, desc, formula }, i) => (
                <article key={title} className={styles.featureCard}>
                  <div className={styles.featureCardTop}>
                    <div className={styles.featureSigil}>{sigil}</div>
                  </div>
                  <div className={styles.featureArcana}>{arcana}</div>
                  <Heading as="h3" className={styles.featureTitle}>{title}</Heading>
                  <p className={styles.featureDesc}>{desc}</p>
                  <div className={styles.featureFormula}>{formula}</div>
                </article>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className={styles.homeFooter}>
        <span>© 2026 SUZENT</span>
      </footer>
    </Layout>
  );
}
