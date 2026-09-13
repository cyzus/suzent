import copyData from "../../../content/sovereignty.json";
import type { ReactNode } from "react";
import Link from "next/link";
import { localePath, type Locale } from "@/lib/locales";
import { SiteNav } from "../site-nav";

import styles from "./sovereign.module.css";

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
  pillars: Array<{
    index: string;
    title: string;
    description: string;
    formula: string;
  }>;
  testLabel: string;
  testTitle: string;
  testIntro: string;
  tests: Array<{ question: string; answer: string }>;
  testResult: string;
  proofLabel: string;
  proofTitle: string;
  proofs: Array<{
    title: string;
    description: string;
    linkLabel: string;
    to: string;
  }>;
  ctaTitle: string;
  ctaDescription: string;
  quickstart: string;
  github: string;
};

export const COPY: Record<"en" | "zh-Hans", SovereignCopy> = copyData;

export default function Sovereign({ locale }: { locale: Locale }): ReactNode {
  const isZh = locale === "zh-Hans";
  const copy = COPY[isZh ? "zh-Hans" : "en"];
  const pageUrl = isZh
    ? "https://suzent.com/zh-Hans/sovereign"
    : "https://suzent.com/sovereign";

  return (
    <>
      <SiteNav />

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@graph": [
              {
                "@type": "WebPage",
                "@id": `${pageUrl}#webpage`,
                name: `${copy.metaTitle} | Suzent`,
                description: copy.metaDescription,
                url: pageUrl,
                inLanguage: isZh ? "zh-Hans" : "en",
                isPartOf: { "@id": "https://suzent.com/#website" },
                mainEntity: { "@id": `${pageUrl}#definedterm` },
              },
              {
                "@type": "DefinedTerm",
                "@id": `${pageUrl}#definedterm`,
                name: isZh ? "主权 AI 智能体" : "Sovereign AI Agent",
                alternateName: isZh
                  ? ["主权智能体", "智能体主权", "Sovereign AI Agent"]
                  : ["Sovereign Agent", "Agent Sovereignty"],
                description: copy.definition,
                url: pageUrl,
                inDefinedTermSet: {
                  "@type": "DefinedTermSet",
                  name: isZh ? "主权协议" : "The Sovereignty Protocol",
                  url: pageUrl,
                },
                subjectOf: { "@id": `${pageUrl}#webpage` },
                exampleOfWork: {
                  "@type": "SoftwareApplication",
                  "@id": "https://suzent.com/#software",
                  name: "Suzent",
                },
                hasPart: copy.pillars.map((pillar) => ({
                  "@type": "DefinedTerm",
                  name: pillar.title,
                  description: pillar.description,
                })),
              },
              {
                "@type": "FAQPage",
                "@id": `${pageUrl}#faq`,
                inLanguage: isZh ? "zh-Hans" : "en",
                isPartOf: { "@id": `${pageUrl}#webpage` },
                mainEntity: copy.tests.map((test) => ({
                  "@type": "Question",
                  name: test.question,
                  acceptedAnswer: {
                    "@type": "Answer",
                    text: test.answer,
                  },
                })),
              },
            ],
          }).replace(/</g, "\\u003c"),
        }}
      />

      <main className={styles.page}>
        <header className={styles.hero}>
          <div className={styles.heroGrid} aria-hidden="true" />
          <div className={styles.container}>
            <p className={styles.eyebrow}>{copy.eyebrow}</p>
            <h1 className={styles.title}>{copy.title}</h1>
            <p className={styles.intro}>{copy.intro}</p>
            <p className={styles.answer}>{copy.answer}</p>
          </div>
        </header>

        <section className={styles.section}>
          <div className={styles.container}>
            <p className={styles.sectionLabel}>{copy.definitionLabel}</p>
            <h2 className={styles.definitionTitle}>{copy.definitionTitle}</h2>
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
                  <h2 className={styles.pillarTitle}>{pillar.title}</h2>
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
                <h2 className={styles.sectionTitle}>{copy.testTitle}</h2>
                <p className={styles.testIntro}>{copy.testIntro}</p>
              </div>
              <ol className={styles.testList}>
                {copy.tests.map((test, index) => (
                  <li key={test.question}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
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
            <h2 className={styles.sectionTitle}>{copy.proofTitle}</h2>
            <div className={styles.proofGrid}>
              {copy.proofs.map((proof) => (
                <article className={styles.proof} key={proof.title}>
                  <h3>{proof.title}</h3>
                  <p>{proof.description}</p>
                  <Link href={localePath(proof.to, locale)}>
                    {proof.linkLabel} →
                  </Link>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.cta}>
          <div className={styles.container}>
            <h2>{copy.ctaTitle}</h2>
            <p>{copy.ctaDescription}</p>
            <div className={styles.actions}>
              <Link
                className={styles.primaryAction}
                href={localePath("/docs/getting-started/quickstart", locale)}
              >
                {copy.quickstart}
              </Link>
              <a
                className={styles.secondaryAction}
                href="https://github.com/cyzus/suzent"
              >
                {copy.github}
              </a>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}
