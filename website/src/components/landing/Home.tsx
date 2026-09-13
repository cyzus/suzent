"use client";
import { useState, useEffect, useRef, type ReactNode } from "react";
import clsx from "clsx";
import Link from "next/link";
import { useLocale, useTranslator, localePath } from "../locale";
import { SiteNav } from "../site-nav";
import { HeroArt } from "./HeroArt";
import { DotCube, type DotFieldPointer } from "./DotSphere";
import styles from "./index.module.css";

const UNIX_CMD = `curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash`;
const WIN_CMD = `powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"`;

const getFeatureCards = (translate: ReturnType<typeof useTranslator>) => [
  {
    arcana: translate({
      id: "homepage.features.modelAgnostic.arcana",
      message: "I · SOVEREIGN MIND",
    }),
    sigil: "⊕",
    title: translate({
      id: "homepage.features.modelAgnostic.title",
      message: "Choose the Model. Keep the Self.",
    }),
    desc: translate({
      id: "homepage.features.modelAgnostic.desc",
      message:
        "Models are replaceable engines. Identity, memory, skills, and workspace remain yours when the provider changes.",
    }),
    formula: "model ≠ identity",
  },
  {
    arcana: translate({
      id: "homepage.features.private.arcana",
      message: "II · SOVEREIGN AUTHORITY",
    }),
    sigil: "□",
    title: translate({
      id: "homepage.features.private.title",
      message: "Your Agent, Under Your Law",
    }),
    desc: translate({
      id: "homepage.features.private.desc",
      message:
        "Permissions, scoped rules, sandbox boundaries, and an inspectable activity trail keep every action under your authority.",
    }),
    formula: "action ⊆ your law",
  },
  {
    arcana: translate({
      id: "homepage.features.automation.arcana",
      message: "III · SOVEREIGN VESSEL",
    }),
    sigil: "⌁",
    title: translate({
      id: "homepage.features.automation.title",
      message: "Run Where You Hold the Keys",
    }),
    desc: translate({
      id: "homepage.features.automation.desc",
      message:
        "Control the runtime, isolate project workspaces, mount your own folders, and extend the agent only to approved devices.",
    }),
    formula: "runtime ∈ your domain",
  },
  {
    arcana: translate({
      id: "homepage.features.crossPlatform.arcana",
      message: "IV · SOVEREIGN CONTINUITY",
    }),
    sigil: "△",
    title: translate({
      id: "homepage.features.crossPlatform.title",
      message: "Outlive Any Platform",
    }),
    desc: translate({
      id: "homepage.features.crossPlatform.desc",
      message:
        "Move memory, skills, and configuration while credentials stay local. Models and machines can change; your agent remains.",
    }),
    formula: "self > platform",
  },
];

// ─── Utilities ────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }): ReactNode {
  const translate = useTranslator();
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    },
    [],
  );
  const copy = async (): Promise<void> => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setFailed(false);
    } catch {
      setFailed(true);
    }
    timeoutRef.current = setTimeout(() => {
      setCopied(false);
      setFailed(false);
    }, 2000);
  };
  return (
    <button
      className={clsx(styles.copyBtn, copied && styles.copyBtnDone)}
      onClick={copy}
    >
      {failed
        ? translate({ id: "homepage.copy.failed", message: "COPY FAILED" })
        : copied
          ? translate({ id: "homepage.copy.sealed", message: "SEALED" })
          : translate({ id: "homepage.copy.copy", message: "COPY" })}
    </button>
  );
}

function ScrambleTitle({ text }: { text: string }): ReactNode {
  const [displayText, setDisplayText] = useState(text);
  const intervalRef = useRef<number | null>(null);
  const CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ◈⊕⊗◆▲✦—+*";

  useEffect(
    () => () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    },
    [],
  );

  const handleMouseEnter = (): void => {
    let frame = 0;
    const resolved = new Set<number>();
    if (intervalRef.current) window.clearInterval(intervalRef.current);

    intervalRef.current = window.setInterval(() => {
      if (frame > 10 && frame % 3 === 0) {
        const pool = text
          .split("")
          .map((_, i) => i)
          .filter((i) => !resolved.has(i));
        if (pool.length)
          resolved.add(pool[Math.floor(Math.random() * pool.length)]);
      }
      if (resolved.size >= text.length) {
        setDisplayText(text);
        window.clearInterval(intervalRef.current!);
      } else {
        setDisplayText(
          text
            .split("")
            .map((_, i) =>
              resolved.has(i)
                ? text[i]
                : CHARS[Math.floor(Math.random() * CHARS.length)],
            )
            .join(""),
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

// ─── Hero ─────────────────────────────────────────────────────────────────────

function HomepageHeader(): ReactNode {
  const locale = useLocale();
  const translate = useTranslator();
  const [platform, setPlatform] = useState<"unix" | "windows">("unix");
  const [orbPointer, setOrbPointer] = useState<DotFieldPointer>({
    x: 0,
    y: 0,
    active: false,
  });
  const heroOrbRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (navigator.userAgent.includes("Windows")) setPlatform("windows");
  }, []);

  useEffect(() => {
    function updateOrbPointer(
      clientX: number,
      clientY: number,
      active: boolean,
    ) {
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

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerleave", handlePointerLeave);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerleave", handlePointerLeave);
    };
  }, []);

  const installCmd = platform === "windows" ? WIN_CMD : UNIX_CMD;

  return (
    <header className={styles.heroBanner}>
      {/* Above fold — title + orb fills the full viewport */}
      <div className={styles.heroInner}>
        <div className={styles.heroTitleArea}>
          <h1 className={styles.heroTitleBox}>
            <ScrambleTitle text={"SUZENT"} />
          </h1>
          <p className={styles.heroSubtitle}>
            {translate({
              id: "homepage.hero.kicker",
              message: "THE SOVEREIGN AI AGENT",
            })}
          </p>
        </div>

        <div className={styles.heroOrb} ref={heroOrbRef}>
          <DotCube pointer={orbPointer} />
          <HeroArt pointer={orbPointer} />
        </div>

        <p className={styles.heroTagline}>
          {translate({
            id: "homepage.hero.subtitle",
            message: "Models are replaceable. Your agent remains.",
          })}
        </p>
      </div>

      {/* Below fold — install + CTA revealed on scroll */}
      <div className={styles.heroAction}>
        <div className={styles.heroInstall}>
          <div className={styles.installSystemBar}>
            <span>
              {translate({
                id: "homepage.install.status",
                message: "RITUAL STATUS: LISTENING",
              })}
            </span>
            <span>
              {translate({
                id: "homepage.install.saasJab",
                message: "NO SUBSCRIPTION ALTAR REQUIRED",
              })}
            </span>
          </div>
          <div className={styles.platformTabs}>
            <button
              className={clsx(
                styles.platformTab,
                platform === "unix" && styles.platformTabActive,
              )}
              onClick={() => setPlatform("unix")}
            >
              {translate({
                id: "homepage.install.unix",
                message: "Linux/Mac Rite",
              })}
            </button>
            <button
              className={clsx(
                styles.platformTab,
                platform === "windows" && styles.platformTabActive,
              )}
              onClick={() => setPlatform("windows")}
            >
              {translate({
                id: "homepage.install.windows",
                message: "Windows Rite",
              })}
            </button>
          </div>
          <div className={styles.cmdLabel}>
            {translate({
              id: "homepage.install.invocation",
              message: "Invocation Script",
            })}
          </div>
          <div className={styles.cmdRow}>
            <pre className={styles.cmdText}>{installCmd}</pre>
            <CopyButton text={installCmd} />
          </div>
          <div className={styles.installDivider}>
            <span className={styles.installDividerLine} />
            <span className={styles.installDividerLabel}>
              {translate({
                id: "homepage.install.thenRun",
                message: "then run",
              })}
            </span>
            <span className={styles.installDividerLine} />
          </div>
          <div className={styles.cmdLabel}>
            {translate({
              id: "homepage.install.vessel",
              message: "Open Vessel",
            })}
          </div>
          <div className={styles.cmdRow}>
            <pre className={styles.cmdText}>suzent start</pre>
            <CopyButton text="suzent start" />
          </div>
        </div>

        <div className={styles.heroCta}>
          <Link
            className={styles.heroCtaBtn}
            href={localePath("/docs/getting-started/quickstart", locale)}
          >
            {translate({
              id: "homepage.hero.cta.primary",
              message: "Summon Suzent",
            })}
          </Link>
          <Link
            className={clsx(styles.heroCtaBtn, styles.heroCtaBtnSecondary)}
            href={localePath("/sovereign", locale)}
          >
            {translate({
              id: "homepage.hero.cta.sovereign",
              message: "Read the Sovereignty Protocol",
            })}
          </Link>
        </div>
      </div>
    </header>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Home(): ReactNode {
  const locale = useLocale();
  const translate = useTranslator();
  const FEATURE_CARDS = getFeatureCards(translate);
  return (
    <div className="landing">
      <SiteNav />
      <HomepageHeader />

      <main>
        <section className={styles.featuresSection}>
          <div className="container">
            <div className={styles.featuresHeader}>
              <span className={styles.featuresRuleLine} />
              <span className={styles.featuresRuleLabel}>
                {translate({
                  id: "homepage.features.label",
                  message: "WHAT MAKES AN AGENT SOVEREIGN?",
                })}
              </span>
              <span className={styles.featuresRuleLine} />
            </div>
            <div className={styles.grid}>
              {FEATURE_CARDS.map(
                ({ arcana, sigil, title, desc, formula }, i) => (
                  <article key={title} className={styles.featureCard}>
                    <div className={styles.featureCardTop}>
                      <div className={styles.featureSigil}>{sigil}</div>
                    </div>
                    <div className={styles.featureArcana}>{arcana}</div>
                    <h3 className={styles.featureTitle}>{title}</h3>
                    <p className={styles.featureDesc}>{desc}</p>
                    <div className={styles.featureFormula}>{formula}</div>
                  </article>
                ),
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className={styles.homeFooter}>
        <span>© 2026 SUZENT</span>
        <Link href={localePath("/browser-privacy", locale)}>
          {translate({ id: "home.browserPrivacy", message: "Browser privacy" })}
        </Link>
      </footer>
    </div>
  );
}
