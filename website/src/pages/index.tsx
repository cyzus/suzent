import type { ReactNode } from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

import { RobotAvatar } from '@site/src/components/RobotAvatar';
import styles from './index.module.css';

function HomepageHeader() {
  const { siteConfig } = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <div style={{ height: '250px', width: '100%', display: 'flex', justifyContent: 'center', marginBottom: '2rem' }}>
          <div style={{ height: '250px', width: '250px' }}>
            <RobotAvatar variant="peeker" />
          </div>
        </div>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to="/docs/getting-started/quickstart">
            Get Started - 5min ⏱️
          </Link>
          <Link
            className="button button--secondary button--lg button--white"
            to="https://github.com/cyzus/suzent">
            GitHub 📦
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  const { siteConfig } = useDocusaurusContext();
  return (
    <Layout
      title={`Your sovereign digital coworker`}
      description="Description will go into a meta tag in <head />">
      <HomepageHeader />
      <main>
      </main>
    </Layout>
  );
}
