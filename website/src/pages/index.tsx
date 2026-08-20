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
          <Link to="/sovereign" className={styles.homeNavLink}>
            <Translate id="homepage.nav.sovereign">Sovereign</Translate>
          </Link>
          <Link to="/blog" className={styles.homeNavLink}>Blog</Link>
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
