import type { ReactNode } from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import Translate, { translate } from '@docusaurus/Translate';

import { RobotAvatar } from '@site/src/components/RobotAvatar';
import styles from './index.module.css';

function useFeatureCards() {
  return [
    {
      title: translate({ id: 'homepage.features.modelAgnostic.title', message: 'Model-agnostic' }),
      desc: translate({ id: 'homepage.features.modelAgnostic.desc', message: 'Use GPT, Claude, Gemini, and more with one interface. Switch models without rewriting your setup.' }),
    },
    {
      title: translate({ id: 'homepage.features.memory.title', message: 'Persistent memory' }),
      desc: translate({ id: 'homepage.features.memory.desc', message: 'Dual-tier memory: fast markdown recall + semantic LanceDB search. Your agent remembers across sessions.' }),
    },
    {
      title: translate({ id: 'homepage.features.private.title', message: 'Private by default' }),
      desc: translate({ id: 'homepage.features.private.desc', message: 'Local-first architecture with sandboxed execution. Your data stays on your machine.' }),
    },
    {
      title: translate({ id: 'homepage.features.automation.title', message: 'Built-in automation' }),
      desc: translate({ id: 'homepage.features.automation.desc', message: 'Schedule tasks with cron jobs or run continuous heartbeat monitors — no extra tooling needed.' }),
    },
    {
      title: translate({ id: 'homepage.features.skills.title', message: 'Extensible via Skills' }),
      desc: translate({ id: 'homepage.features.skills.desc', message: 'Package domain knowledge as Markdown skills. Drop them in and your agent instantly gains new capabilities.' }),
    },
    {
      title: translate({ id: 'homepage.features.crossPlatform.title', message: 'Cross-platform' }),
      desc: translate({ id: 'homepage.features.crossPlatform.desc', message: 'Works on Windows, macOS, and Linux. Connect companion devices via Nodes over WebSocket.' }),
    },
  ];
}

function useHowItWorksSteps() {
  return [
    {
      step: '01',
      title: translate({ id: 'homepage.howItWorks.install.title', message: 'Install' }),
      desc: translate({ id: 'homepage.howItWorks.install.desc', message: 'Run the install script for your platform. Suzent sets up in under a minute.' }),
    },
    {
      step: '02',
      title: translate({ id: 'homepage.howItWorks.configure.title', message: 'Configure' }),
      desc: translate({ id: 'homepage.howItWorks.configure.desc', message: 'Open Settings → Providers and add your model API key. Choose GPT, Claude, Gemini, or any compatible model.' }),
    },
    {
      step: '03',
      title: translate({ id: 'homepage.howItWorks.launch.title', message: 'Launch' }),
      desc: translate({ id: 'homepage.howItWorks.launch.desc', message: "Run suzent start and you're live — full memory, tools, and automation ready to go." }),
    },
  ];
}

function HomepageHeader() {
  const { siteConfig } = useDocusaurusContext();
  return (
    <header className={clsx('hero', styles.heroBanner)}>
      <div className="container">
        <p className={styles.kicker}>
          <Translate id="homepage.hero.kicker">SOVEREIGN DIGITAL CO-WORKER</Translate>
        </p>
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <div className={styles.heroLayout}>
          <div className={styles.heroText}>
            <p className={styles.subtitle}>
              <Translate id="homepage.hero.subtitle">
                Own your workflows. Keep control of your data. Run AI your way.
              </Translate>
            </p>
            <div className={styles.buttons}>
              <Link
                className="button button--secondary button--lg"
                to="/docs/getting-started/quickstart">
                <Translate id="homepage.hero.cta.primary">Get Started — 5 min</Translate>
              </Link>
              <Link
                className="button button--secondary button--lg button--white"
                to="https://github.com/cyzus/suzent">
                <Translate id="homepage.hero.cta.github">View on GitHub</Translate>
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
  const featureCards = useFeatureCards();
  const howItWorksSteps = useHowItWorksSteps();

  return (
    <Layout
      title={translate({ id: 'homepage.meta.title', message: 'Your sovereign digital coworker' })}
      description={translate({ id: 'homepage.meta.description', message: 'Model-agnostic, local-first AI agent with persistent memory, built-in automation, and full data sovereignty.' })}>
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
            <Heading as="h2" className={styles.sectionHeading}>
              <Translate id="homepage.howItWorks.heading">How it works</Translate>
            </Heading>
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
            <Heading as="h2">
              <Translate id="homepage.callout.heading">Start in 5 minutes</Translate>
            </Heading>
            <p>
              <Translate id="homepage.callout.desc">
                Install Suzent, configure your model key, and launch your first local agent session.
              </Translate>
            </p>
            <div className={styles.calloutButtons}>
              <Link className={`button button--lg ${styles.calloutPrimaryButton}`} to="/docs/getting-started/quickstart">
                <Translate id="homepage.callout.cta.primary">Open Quickstart</Translate>
              </Link>
              <Link className={`button button--lg ${styles.calloutSecondaryButton}`} to="/docs/concepts/tools">
                <Translate id="homepage.callout.cta.secondary">Explore Core Tools</Translate>
              </Link>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
