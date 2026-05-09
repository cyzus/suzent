import { useState, useEffect, useRef, type ReactNode } from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import Head from '@docusaurus/Head';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import Translate, { translate } from '@docusaurus/Translate';
import { useColorMode } from '@docusaurus/theme-common';

import { HeroArt } from '@site/src/components/HeroArt';
import {
  IconModelAgnostic,
  IconMemory,
  IconLock,
  IconClock,
  IconSkills,
  IconTerminal,
} from '@site/src/components/FeatureIcon';
import styles from './index.module.css';

const UNIX_CMD = `curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash`;
const WIN_CMD  = `irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex`;


const FEATURE_CARDS = [
  {
    Icon: IconModelAgnostic,
    title: translate({ id: 'homepage.features.modelAgnostic.title', message: 'Model-agnostic' }),
    desc: translate({ id: 'homepage.features.modelAgnostic.desc', message: 'Use GPT, Claude, Gemini, and more with one interface. Switch models without rewriting your setup.' }),
  },
  {
    Icon: IconMemory,
    title: translate({ id: 'homepage.features.memory.title', message: 'Persistent memory' }),
    desc: translate({ id: 'homepage.features.memory.desc', message: 'Dual-tier memory: fast markdown recall + semantic LanceDB search. Your agent remembers across sessions.' }),
  },
  {
    Icon: IconLock,
    title: translate({ id: 'homepage.features.private.title', message: 'Private by default' }),
    desc: translate({ id: 'homepage.features.private.desc', message: 'Local-first architecture with sandboxed execution. Your data stays on your machine.' }),
  },
  {
    Icon: IconClock,
    title: translate({ id: 'homepage.features.automation.title', message: 'Built-in automation' }),
    desc: translate({ id: 'homepage.features.automation.desc', message: 'Schedule tasks with cron jobs or run continuous heartbeat monitors — no extra tooling needed.' }),
  },
  {
    Icon: IconSkills,
    title: translate({ id: 'homepage.features.skills.title', message: 'Extensible via Skills' }),
    desc: translate({ id: 'homepage.features.skills.desc', message: 'Package domain knowledge as Markdown skills. Drop them in and your agent instantly gains new capabilities.' }),
  },
  {
    Icon: IconTerminal,
    title: translate({ id: 'homepage.features.crossPlatform.title', message: 'Cross-platform' }),
    desc: translate({ id: 'homepage.features.crossPlatform.desc', message: 'Works on Windows, macOS, and Linux. Connect companion devices via Nodes over WebSocket.' }),
  },
];

function HomepageNav() {
  const { colorMode, setLightTheme, setDarkTheme } = useColorMode();
  return (
    <nav className={styles.homeNav} aria-label="Homepage navigation">
      <div className={styles.homeNavInner}>
        <Link to="/" className={styles.homeNavBrand}>
          <span className={styles.homeNavMark} aria-hidden="true">
            <span /><span />
          </span>
          <span className={styles.homeNavTitle}>SUZENT</span>
        </Link>
        <div className={styles.homeNavLinks}>
          <Link to="/docs/getting-started/intro" className={styles.homeNavLink}>Docs</Link>
          <a
            href="https://github.com/cyzus/suzent"
            className={styles.homeNavLink}
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
          <a
            href="https://discord.gg/suzent"
            className={styles.homeNavLink}
            target="_blank"
            rel="noopener noreferrer"
          >
            Discord
          </a>
          <button
            className={styles.themeToggleBtn}
            onClick={() => colorMode === 'dark' ? setLightTheme() : setDarkTheme()}
            aria-label="Toggle dark mode"
          >
            {colorMode === 'dark' ? '☀️' : '🌙'}
          </button>
        </div>
      </div>
    </nav>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button className={clsx(styles.copyBtn, copied && styles.copyBtnDone)} onClick={copy}>
      {copied ? '✓ COPIED' : 'COPY'}
    </button>
  );
}

function ScrambleTitle({ text }: { text: string }) {
  const [displayText, setDisplayText] = useState(text);
  const intervalRef = useRef<number | null>(null);

  const handleMouseEnter = () => {
    let frame = 0;
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ!<>-_\\/[]{}—=+*^?#_';
    const resolvedIndices = new Set<number>();
    
    if (intervalRef.current) window.clearInterval(intervalRef.current);

    intervalRef.current = window.setInterval(() => {
      // 1. Mutate state (lock characters over time)
      if (frame > 10) {
        if (frame % 3 === 0) {
          const unresolved = text.split('').map((_, i) => i).filter(i => !resolvedIndices.has(i));
          if (unresolved.length > 0) {
            const randomIndex = unresolved[Math.floor(Math.random() * unresolved.length)];
            resolvedIndices.add(randomIndex);
          }
        }
      }
      
      // 2. Render current state
      if (resolvedIndices.size >= text.length) {
        setDisplayText(text); // Force exact original text at the end
        window.clearInterval(intervalRef.current!);
      } else {
        setDisplayText(
          text
            .split('')
            .map((letter, index) => {
              if (resolvedIndices.has(index)) {
                return text[index];
              }
              return chars[Math.floor(Math.random() * chars.length)];
            })
            .join('')
        );
      }
      
      frame++;
    }, 30);
  };

  return (
    <span 
      className={styles.heroTitleInner} 
      data-text={displayText}
      onMouseEnter={handleMouseEnter}
    >
      {displayText}
    </span>
  );
}

function HomepageHeader() {
  const { siteConfig } = useDocusaurusContext();
  const [platform, setPlatform] = useState<'unix' | 'windows'>('unix');

  useEffect(() => {
    if (navigator.userAgent.includes('Windows')) setPlatform('windows');
  }, []);

  const installCmd = platform === 'windows' ? WIN_CMD : UNIX_CMD;

  return (
    <header className={clsx('hero', styles.heroBanner)}>
      <div className={clsx('container', styles.heroContainer)}>
        <div className={styles.heroLayout}>

          <div className={styles.heroText}>
            <span className={styles.kickerChip}>
              <Translate id="homepage.hero.kicker">SOVEREIGN DIGITAL CO-WORKER</Translate>
            </span>
            <div className={styles.heroTitleBox}>
              <ScrambleTitle text={siteConfig.title} />
            </div>
            <p className={styles.subtitle}>
              <Translate id="homepage.hero.subtitle">
                Runs local. Thinks fast. Forgets nothing.
              </Translate>
            </p>

            {/* Install block */}
            <div className={styles.heroInstall}>
              <div className={styles.platformTabs}>
                <button
                  className={clsx(styles.platformTab, platform === 'unix' && styles.platformTabActive)}
                  onClick={() => setPlatform('unix')}
                >
                  Mac / Linux
                </button>
                <button
                  className={clsx(styles.platformTab, platform === 'windows' && styles.platformTabActive)}
                  onClick={() => setPlatform('windows')}
                >
                  Windows
                </button>
              </div>
              <div className={styles.cmdRow}>
                <pre className={styles.cmdText}>{installCmd}</pre>
                <CopyButton text={installCmd} />
              </div>
              <div className={styles.installDivider}>
                <span className={styles.installDividerLabel}>then run</span>
              </div>
              <div className={styles.cmdRow}>
                <pre className={styles.cmdText}>{'suzent start'}</pre>
                <CopyButton text="suzent start" />
              </div>
            </div>

            {/* CTA buttons */}
            <div className={styles.buttons}>
              <Link
                className={`button button--lg ${styles.heroPrimaryButton}`}
                to="/docs/getting-started/quickstart">
                <Translate id="homepage.hero.cta.primary">Get Started — 5 min</Translate>
              </Link>
            </div>
          </div>

          <div className={styles.heroRobotCol}>
            <div className={styles.heroLogo}>
              <HeroArt />
            </div>
          </div>

        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {

  return (
    <Layout
      title={translate({ id: 'homepage.meta.title', message: 'Your sovereign digital coworker' })}
      description={translate({ id: 'homepage.meta.description', message: 'Model-agnostic, local-first AI agent with persistent memory, built-in automation, and full data sovereignty.' })}>

      <Head>
        <style>{`.navbar,.navbar--fixed-top{display:none!important}`}</style>
      </Head>
      <HomepageNav />
      <HomepageHeader />

      <main>
        <section className={styles.featuresSection}>
          <div className="container">
            <div className={styles.grid}>
              {FEATURE_CARDS.map(({ Icon, title, desc }) => (
                <article key={title} className={styles.featureCard}>
                  <div className={styles.featureIconBox}>
                    <Icon className={styles.featureSvg} />
                  </div>
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
