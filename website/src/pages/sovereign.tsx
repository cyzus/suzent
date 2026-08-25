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
  definitionLabel: string;
  definitionTitle: string;
  definition: string;
  disambiguation: string;
  pillarsLabel: string;
  pillars: Array<{ index: string; title: string; description: string; formula: string }>;
  testLabel: string;
  testTitle: string;
  testIntro: string;
  tests: Array<{ question: string; answer: string }>;
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
    metaTitle: 'What Is a Sovereign AI Agent?',
    metaDescription: 'A sovereign AI agent is an agent whose identity, memory, skills, workspace, and runtime you own rather than rent. The four conditions, a five-question ownership test, and how Suzent implements them.',
    eyebrow: '{ ∅ } / THE SOVEREIGNTY PROTOCOL',
    title: 'WHAT MAKES AN AGENT SOVEREIGN?',
    intro: 'Sovereignty is not merely running an agent on your laptop. It is the power to own its memory, choose its intelligence, govern its actions, and preserve its identity beyond any model or platform.',
    answer: 'Suzent’s answer to who holds that power is always the same: you.',
    definitionLabel: 'DEFINITION',
    definitionTitle: 'What is a sovereign AI agent?',
    definition: 'A sovereign AI agent is an AI agent whose identity, memory, skills, workspace, and runtime are owned and governed by its user rather than by a model provider or platform. Its durable state lives in files you can read, edit, version, and move; its actions run inside permission boundaries you define; and replacing the underlying model does not reset the agent that knows your work. Suzent is an open-source, local-first implementation of that definition.',
    disambiguation: 'The phrase “sovereign AI” is also used at the scale of nations, for state-controlled models, data, and compute. A sovereign agent applies the same idea at the scale of a person: sovereignty over one agent, held by the individual who runs it.',
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
      {
        question: 'Can I inspect, edit, version, and delete its memory?',
        answer: 'In Suzent, memory is append-only Markdown on your own disk. You can open it in any editor, track it in Git, and delete it without a vendor’s permission. The search index serves those files and can be rebuilt from them.',
      },
      {
        question: 'Can I replace the model without resetting its identity?',
        answer: 'Identity lives in memory, skills, context, and workspace — not in the model. Switching between GPT, Claude, Gemini, DeepSeek, or a local model leaves the agent that knows your work intact.',
      },
      {
        question: 'Can I define, approve, and audit what it is allowed to do?',
        answer: 'Tool calls pass through permission modes you set, with human approval gates and scoped rules governing which actions may cross from reasoning into execution.',
      },
      {
        question: 'Can I move its state without exporting my credentials?',
        answer: 'Portable agent state syncs separately from machine-local secrets, so moving to a new machine never requires shipping your API keys along with it.',
      },
      {
        question: 'Can the agent survive the disappearance of its provider?',
        answer: 'Everything that defines the agent is already files you hold. A provider shutting down costs you an API key, not an agent.',
      },
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
    metaTitle: '什么是主权 AI 智能体？',
    metaDescription: '主权 AI 智能体，是指身份、记忆、技能、工作区和运行环境由你拥有而非租用的智能体。本文给出四个必要条件、五个所有权检验问题，以及 Suzent 的具体实现。',
    eyebrow: '{ ∅ } / 主权协议',
    title: '什么才是主权智能体？',
    intro: '主权不只是把智能体运行在自己的电脑上，而是你能够拥有它的记忆、选择它的智能、治理它的行动，并让它的身份跨越任何模型和平台继续存在。',
    answer: '谁应该拥有这些权力？Suzent 的答案始终是：你。',
    definitionLabel: '定义',
    definitionTitle: '什么是主权 AI 智能体？',
    definition: '主权 AI 智能体（sovereign AI agent）是指身份、记忆、技能、工作区和运行环境由使用者本人拥有和治理，而不是由模型提供商或平台掌握的 AI 智能体。它的持久状态保存在你可以阅读、编辑、版本管理和迁移的文件中；它的行动运行在你定义的权限边界内；更换底层模型也不会重置这个了解你工作的智能体。Suzent 就是这一定义的开源、本地优先实现。',
    disambiguation: '“主权 AI”这个说法也被用在国家层面，指国家掌控的模型、数据和算力。主权智能体把同样的理念放到个人尺度：一个智能体的主权，属于运行它的那个人。',
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
      {
        question: '我能否检查、编辑、版本管理和删除它的记忆？',
        answer: '在 Suzent 中，记忆是保存在你自己磁盘上的追加式 Markdown 文件。你可以用任意编辑器打开、用 Git 管理版本，也可以随时删除，无需任何厂商许可。搜索索引服务于这些文件，并且可以从文件重建。',
      },
      {
        question: '我能否更换模型，而不重置它的身份？',
        answer: '身份存在于记忆、技能、上下文和工作区中，而不在模型里。在 GPT、Claude、Gemini、DeepSeek 或本地模型之间切换，都不会影响这个了解你工作的智能体。',
      },
      {
        question: '我能否定义、审批并审计它被允许执行的行动？',
        answer: '工具调用会经过你设定的权限模式，由人工审批和作用域规则决定哪些行动可以从推理跨越到真实执行。',
      },
      {
        question: '我能否迁移它的状态，而不导出自己的凭证？',
        answer: '可迁移的智能体状态与设备本地的密钥分开同步，因此换一台机器时不必把 API 密钥一起带走。',
      },
      {
        question: '如果提供商消失，这个智能体还能继续存在吗？',
        answer: '定义这个智能体的一切，本来就是你手中的文件。提供商关停让你失去的是一个 API 密钥，而不是一个智能体。',
      },
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
  const isZh = i18n.currentLocale === 'zh-Hans';
  const copy = COPY[isZh ? 'zh-Hans' : 'en'];
  const pageUrl = isZh
    ? 'https://suzent.com/zh-Hans/sovereign'
    : 'https://suzent.com/sovereign';

  return (
    <Layout title={copy.metaTitle} description={copy.metaDescription}>
      <Head>
        <script type="application/ld+json">
          {JSON.stringify({
            '@context': 'https://schema.org',
            '@graph': [
              {
                '@type': 'WebPage',
                '@id': `${pageUrl}#webpage`,
                name: `${copy.metaTitle} | Suzent`,
                description: copy.metaDescription,
                url: pageUrl,
                inLanguage: isZh ? 'zh-Hans' : 'en',
                isPartOf: { '@id': 'https://suzent.com/#website' },
                mainEntity: { '@id': `${pageUrl}#definedterm` },
              },
              {
                '@type': 'DefinedTerm',
                '@id': `${pageUrl}#definedterm`,
                name: isZh ? '主权 AI 智能体' : 'Sovereign AI Agent',
                alternateName: isZh
                  ? ['主权智能体', '智能体主权', 'Sovereign AI Agent']
                  : ['Sovereign Agent', 'Agent Sovereignty'],
                description: copy.definition,
                url: pageUrl,
                inDefinedTermSet: {
                  '@type': 'DefinedTermSet',
                  name: isZh ? '主权协议' : 'The Sovereignty Protocol',
                  url: pageUrl,
                },
                subjectOf: { '@id': `${pageUrl}#webpage` },
                exampleOfWork: {
                  '@type': 'SoftwareApplication',
                  '@id': 'https://suzent.com/#software',
                  name: 'Suzent',
                },
                hasPart: copy.pillars.map((pillar) => ({
                  '@type': 'DefinedTerm',
                  name: pillar.title,
                  description: pillar.description,
                })),
              },
              {
                '@type': 'FAQPage',
                '@id': `${pageUrl}#faq`,
                inLanguage: isZh ? 'zh-Hans' : 'en',
                isPartOf: { '@id': `${pageUrl}#webpage` },
                mainEntity: copy.tests.map((test) => ({
                  '@type': 'Question',
                  name: test.question,
                  acceptedAnswer: {
                    '@type': 'Answer',
                    text: test.answer,
                  },
                })),
              },
            ],
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
            <p className={styles.sectionLabel}>{copy.definitionLabel}</p>
            <Heading as="h2" className={styles.definitionTitle}>{copy.definitionTitle}</Heading>
            <p className={styles.definitionBody}>{copy.definition}</p>
            <p className={styles.disambiguation}>{copy.disambiguation}</p>
          </div>
        </section>

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
                  <li key={test.question}>
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <div>
                      <p>{test.question}</p>
                      <p className={styles.testAnswer}>{test.answer}</p>
                    </div>
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
