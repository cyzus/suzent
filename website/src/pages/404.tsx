import type { ReactNode } from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import { RobotAvatar } from '@site/src/components/RobotAvatar';
import styles from './404.module.css';

export default function NotFound(): ReactNode {
  return (
    <Layout title="404 — Page Not Found" description="This page could not be found.">
      <main className={styles.container}>
        <div className={styles.robot}>
          <RobotAvatar variant="ghost" />
        </div>
        <Heading as="h1" className={styles.title}>404</Heading>
        <p className={styles.subtitle}>This page has vanished into the void.</p>
        <div className={styles.buttons}>
          <Link className="button button--secondary button--lg" to="/">
            Go Home
          </Link>
          <Link className="button button--secondary button--lg button--white" to="/docs/getting-started/quickstart">
            Read the Docs
          </Link>
        </div>
      </main>
    </Layout>
  );
}
