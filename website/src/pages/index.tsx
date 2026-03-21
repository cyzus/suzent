import type { ReactNode } from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

import { RobotAvatar } from '@site/src/components/RobotAvatar';
import styles from './index.module.css';

const featureCards = [
  {
    title: 'Model-agnostic',
    desc: 'Use GPT, Claude, Gemini, and more with one interface. Switch models without rewriting your setup.',
  },
  {
    title: 'Persistent memory',
    desc: 'Dual-tier memory: fast markdown recall + semantic LanceDB search. Your agent remembers across sessions.',
  },
  {
    title: 'Private by default',
    desc: 'Local-first architecture with sandboxed execution. Your data stays on your machine.',
  },
  {
    title: 'Built-in automation',
    desc: 'Schedule tasks with cron jobs or run continuous heartbeat monitors — no extra tooling needed.',
  },
  {
    title: 'Extensible via Skills',
    desc: 'Package domain knowledge as Markdown skills. Drop them in and your agent instantly gains new capabilities.',
  },
  {
    title: 'Cross-platform',
    desc: 'Works on Windows, macOS, and Linux. Connect companion devices via Nodes over WebSocket.',
  },
];

const howItWorksSteps = [
  {
    step: '01',
    title: 'Install',
    desc: 'Run the install script for your platform. Suzent sets up in under a minute.',
  },
  {
    step: '02',
    title: 'Configure',
    desc: 'Add your model API key to .env. Choose GPT, Claude, Gemini, or any compatible model.',
  },
  {
    step: '03',
    title: 'Launch',
    desc: 'Run suzent start and you\'re live — full memory, tools, and automation ready to go.',
  },
];

function HomepageHeader() {
  const { siteConfig } = useDocusaurusContext();
  return (
    <header className={clsx('hero', styles.heroBanner)}>
      <div className="container">
        <p className={styles.kicker}>SOVEREIGN DIGITAL CO-WORKER</p>
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <div className={styles.heroLayout}>
          <div className={styles.heroText}>
            <p className={styles.subtitle}>Own your workflows. Keep control of your data. Run AI your way.</p>
            <div className={styles.buttons}>
              <Link
                className="button button--secondary button--lg"
                to="/docs/getting-started/quickstart">
                Get Started — 5 min
              </Link>
              <Link
                className="button button--secondary button--lg button--white"
                to="https://github.com/cyzus/suzent">
                View on GitHub
              </Link>
            </div>
          </div>
          <div className={styles.heroRobot}>
            <RobotAvatar variant="peeker" />
          </div>
        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout
      title={`Your sovereign digital coworker`}
      description="SOVEREIGN digital coworker: model-agnostic, local-first, and automation-ready.">
      <HomepageHeader />
      <main className={styles.main}>
        <section className="container">
          <div className={styles.grid}>
            {featureCards.map((item) => (
              <article key={item.title} className={styles.featureCard}>
                <Heading as="h3">{item.title}</Heading>
                <p>{item.desc}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.howItWorksSection}>
          <div className="container">
            <Heading as="h2" className={styles.sectionHeading}>How it works</Heading>
            <div className={styles.stepsGrid}>
              {howItWorksSteps.map((item) => (
                <div key={item.step} className={styles.step}>
                  <span className={styles.stepNumber}>{item.step}</span>
                  <Heading as="h3">{item.title}</Heading>
                  <p>{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="container">
          <div className={styles.callout}>
            <Heading as="h2">Start in 5 minutes</Heading>
            <p>Install Suzent, configure your model key, and launch your first local agent session.</p>
            <div className={styles.calloutButtons}>
              <Link className={`button button--lg ${styles.calloutPrimaryButton}`} to="/docs/getting-started/quickstart">
                Open Quickstart
              </Link>
              <Link className={`button button--lg ${styles.calloutSecondaryButton}`} to="/docs/concepts/tools">
                Explore Core Tools
              </Link>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
