import type { ReactNode } from 'react';
import Head from '@docusaurus/Head';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

import styles from './sovereign.module.css';

type SovereignCopy = {
  metaTitle: string;
  metaDescription: string;
  eyebrow: string;
  title: string;
  intro: string;
  answer: string;
  pillarsLabel: string;
  pillars: Array<{ index: string; title: string; description: string; formula: string }>;
  testLabel: string;
  testTitle: string;
  testIntro: string;
  tests: string[];
  testResult: string;
  proofLabel: string;
  proofTitle: string;
  proofs: Array<{ title: string; description: string; linkLabel: string; to: string }>;
  ctaTitle: string;
  ctaDescription: string;
  quickstart: string;
  github: string;
};

const COPY: Record<'en' | 'zh-Hans', SovereignCopy> = {
  en: {
    metaTitle: 'The Sovereignty Protocol',
    metaDescription: 'A practical definition of sovereign AI agents—and how Suzent keeps identity, authority, runtime, and continuity under your control.',
    eyebrow: '{ ∅ } / THE SOVEREIGNTY PROTOCOL',
    title: 'WHAT MAKES AN AGENT SOVEREIGN?',
    intro: 'Sovereignty is not merely running an agent on your laptop. It is the power to own its memory, choose its intelligence, govern its actions, and preserve its identity beyond any model or platform.',
    answer: 'Suzent’s answer to who holds that power is always the same: you.',
    pillarsLabel: 'THE FOUR CONDITIONS',
    pillars: [
      {
        index: 'I',
        title: 'Sovereign Mind',
        description: 'The model is an engine, not the self. You can replace providers while keeping the memory, skills, context, and workspace that define your agent.',
        formula: 'model ≠ identity',
      },
      {
        index: 'II',
        title: 'Sovereign Authority',
        description: 'Autonomy operates under your law. Permissions, scoped rules, approval gates, sandboxes, and activity records make authority explicit and inspectable.',
        formula: 'action ⊆ your law',
      },
      {
        index: 'III',
        title: 'Sovereign Vessel',
        description: 'The agent runs in a domain you control. Its folders, workspaces, services, and connected devices are granted deliberately—not inherited from a platform.',
        formula: 'runtime ∈ your domain',
      },
      {
        index: 'IV',
        title: 'Sovereign Continuity',
        description: 'Memory, skills, and configuration remain portable while credentials stay local. A provider, model, or machine can disappear without taking the agent with it.',
        formula: 'self > platform',
      },
    ],
    testLabel: 'THE SOVEREIGNTY TEST',
    testTitle: 'Ownership should be testable.',
    testIntro: 'Before calling any agent sovereign, ask five questions:',
    tests: [
      'Can I inspect, edit, version, and delete its memory?',
      'Can I replace the model without resetting its identity?',
      'Can I define, approve, and audit what it is allowed to do?',
      'Can I move its state without exporting my credentials?',
      'Can the agent survive the disappearance of its provider?',
    ],
    testResult: 'If the answer depends on a vendor’s permission, the agent is not fully yours.',
    proofLabel: 'PROOF, NOT PROMISES',
    proofTitle: 'How Suzent makes sovereignty concrete',
    proofs: [
      {
        title: 'Readable, file-backed memory',
        description: 'Markdown is the source of truth. The searchable index serves your files, and can be rebuilt from them.',
        linkLabel: 'Inspect memory architecture',
        to: '/docs/concepts/memory',
      },
      {
        title: 'Governed tool execution',
        description: 'Human approval and scoped tool rules define which actions may cross the boundary from reasoning into execution.',
        linkLabel: 'Inspect approval controls',
        to: '/docs/concepts/tools/human-in-the-loop',
      },
      {
        title: 'Isolated project workspaces',
        description: 'Filesystem access and sandboxed workspaces keep agent activity inside boundaries you can understand and control.',
        linkLabel: 'Inspect filesystem boundaries',
        to: '/docs/concepts/filesystem',
      },
      {
        title: 'Portable state, local secrets',
        description: 'Sync the parts that form the agent while keeping machine-specific credentials out of portable state.',
        linkLabel: 'Inspect continuity design',
        to: '/docs/concepts/github-sync',
      },
    ],
    ctaTitle: 'Do not rent an identity. Own an agent.',
    ctaDescription: 'Start locally, choose the model, and keep the parts that matter.',
    quickstart: 'Summon Suzent',
    github: 'Inspect the source',
  },
  'zh-Hans': {
    metaTitle: '主权协议',
    metaDescription: '主权 AI 智能体的可检验定义，以及 Suzent 如何让身份、权力、运行环境和连续性始终由你控制。',
    eyebrow: '{ ∅ } / 主权协议',
    title: '什么才是主权智能体？',
    intro: '主权不只是把智能体运行在自己的电脑上，而是你能够拥有它的记忆、选择它的智能、治理它的行动，并让它的身份跨越任何模型和平台继续存在。',
    answer: '谁应该拥有这些权力？Suzent 的答案始终是：你。',
    pillarsLabel: '四个必要条件',
    pillars: [
      {
        index: 'I',
        title: '主权心智',
        description: '模型是引擎，而不是自我。更换模型提供商时，定义智能体的记忆、技能、上下文和工作区仍然属于你。',
        formula: '模型 ≠ 身份',
      },
      {
        index: 'II',
        title: '主权权力',
        description: '自主行动必须服从你的规则。权限、作用域、审批、沙箱和活动记录，让权力边界明确且可检查。',
        formula: '行动 ⊆ 你的规则',
      },
      {
        index: 'III',
        title: '主权容器',
        description: '智能体运行在你控制的领域。文件夹、工作区、服务和连接设备都由你主动授予，而不是被平台默认接管。',
        formula: '运行环境 ∈ 你的领域',
      },
      {
        index: 'IV',
        title: '主权连续性',
        description: '记忆、技能和配置可以迁移，凭证留在本地。即使提供商、模型或设备消失，智能体也不会随之消失。',
        formula: '自我 > 平台',
      },
    ],
    testLabel: '主权测试',
    testTitle: '所有权必须能够被检验。',
    testIntro: '在称一个智能体为“主权智能体”之前，先问五个问题：',
    tests: [
      '我能否检查、编辑、版本管理和删除它的记忆？',
      '我能否更换模型，而不重置它的身份？',
      '我能否定义、审批并审计它被允许执行的行动？',
      '我能否迁移它的状态，而不导出自己的凭证？',
      '如果提供商消失，这个智能体还能继续存在吗？',
    ],
    testResult: '如果答案取决于厂商是否许可，这个智能体就还不完全属于你。',
    proofLabel: '不是承诺，而是证据',
    proofTitle: 'Suzent 如何让主权落到实处',
    proofs: [
      {
        title: '可读、基于文件的记忆',
        description: 'Markdown 是事实来源。搜索索引服务于你的文件，并且可以从文件重新构建。',
        linkLabel: '查看记忆架构',
        to: '/docs/concepts/memory',
      },
      {
        title: '受治理的工具执行',
        description: '人工审批和有作用域的工具规则，决定哪些行动可以从推理跨越到真实执行。',
        linkLabel: '查看审批控制',
        to: '/docs/concepts/tools/human-in-the-loop',
      },
      {
        title: '隔离的项目工作区',
        description: '文件系统权限和沙箱工作区，让智能体活动始终处于你能够理解和控制的边界内。',
        linkLabel: '查看文件系统边界',
        to: '/docs/concepts/filesystem',
      },
      {
        title: '状态可迁移，秘密留本地',
        description: '同步构成智能体的部分，同时把设备专属凭证排除在可迁移状态之外。',
        linkLabel: '查看连续性设计',
        to: '/docs/concepts/github-sync',
      },
    ],
    ctaTitle: '不要租用一种身份。拥有一个智能体。',
    ctaDescription: '在本地开始，选择你的模型，并把真正重要的部分留在自己手里。',
    quickstart: '召唤 Suzent',
    github: '检查源代码',
  },
};

export default function Sovereign(): ReactNode {
  const { i18n } = useDocusaurusContext();
  const copy = COPY[i18n.currentLocale === 'zh-Hans' ? 'zh-Hans' : 'en'];

  return (
    <Layout title={copy.metaTitle} description={copy.metaDescription}>
      <Head>
        <script type="application/ld+json">
          {JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'WebPage',
            name: `${copy.metaTitle} | Suzent`,
            description: copy.metaDescription,
            url: i18n.currentLocale === 'zh-Hans'
              ? 'https://suzent.com/zh-Hans/sovereign'
              : 'https://suzent.com/sovereign',
            isPartOf: {
              '@type': 'WebSite',
              name: 'Suzent',
              url: 'https://suzent.com/',
            },
          })}
        </script>
      </Head>

      <main className={styles.page}>
        <header className={styles.hero}>
          <div className={styles.heroGrid} aria-hidden="true" />
          <div className={styles.container}>
            <p className={styles.eyebrow}>{copy.eyebrow}</p>
            <Heading as="h1" className={styles.title}>{copy.title}</Heading>
            <p className={styles.intro}>{copy.intro}</p>
            <p className={styles.answer}>{copy.answer}</p>
          </div>
        </header>

        <section className={styles.section}>
          <div className={styles.container}>
            <p className={styles.sectionLabel}>{copy.pillarsLabel}</p>
            <div className={styles.pillarGrid}>
              {copy.pillars.map((pillar) => (
                <article className={styles.pillar} key={pillar.index}>
                  <span className={styles.index}>{pillar.index}</span>
                  <Heading as="h2" className={styles.pillarTitle}>{pillar.title}</Heading>
                  <p>{pillar.description}</p>
                  <code>{pillar.formula}</code>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.testSection}>
          <div className={styles.container}>
            <p className={styles.sectionLabel}>{copy.testLabel}</p>
            <div className={styles.testLayout}>
              <div>
                <Heading as="h2" className={styles.sectionTitle}>{copy.testTitle}</Heading>
                <p className={styles.testIntro}>{copy.testIntro}</p>
              </div>
              <ol className={styles.testList}>
                {copy.tests.map((test, index) => (
                  <li key={test}>
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <p>{test}</p>
                  </li>
                ))}
              </ol>
            </div>
            <p className={styles.verdict}>{copy.testResult}</p>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.container}>
            <p className={styles.sectionLabel}>{copy.proofLabel}</p>
            <Heading as="h2" className={styles.sectionTitle}>{copy.proofTitle}</Heading>
            <div className={styles.proofGrid}>
              {copy.proofs.map((proof) => (
                <article className={styles.proof} key={proof.title}>
                  <Heading as="h3">{proof.title}</Heading>
                  <p>{proof.description}</p>
                  <Link to={proof.to}>{proof.linkLabel} →</Link>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.cta}>
          <div className={styles.container}>
            <Heading as="h2">{copy.ctaTitle}</Heading>
            <p>{copy.ctaDescription}</p>
            <div className={styles.actions}>
              <Link className={styles.primaryAction} to="/docs/getting-started/quickstart">{copy.quickstart}</Link>
              <a className={styles.secondaryAction} href="https://github.com/cyzus/suzent">{copy.github}</a>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
