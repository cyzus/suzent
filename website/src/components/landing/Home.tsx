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
      data-text={text}
      aria-label={text}
      onMouseEnter={handleMouseEnter}
    >
      {text.split("").map((character, index) => (
        <span className={styles.titleCell} key={index} aria-hidden="true">
          <span className={styles.titleMeasure}>{character}</span>
          <span className={styles.titleGlyph}>{displayText[index]}</span>
        </span>
      ))}
    </span>
  );
}

type InstallerOS = "macos" | "windows" | "linux";

function OSIcon({ os }: { os: InstallerOS }): ReactNode {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="currentColor"
      aria-hidden="true"
    >
      {os === "windows" ? (
        <path d="M2 4l9-1.2v8.3H2zm10-1.4L22 1v10.1H12zM2 12h9v8.3L2 19zm10 0h10v11l-10-1.6z" />
      ) : os === "macos" ? (
        <path d="M16.7 1c.2 1.5-.5 3-1.4 4-.9 1-2.4 1.6-3.8 1.5-.2-1.5.5-3 1.4-4C13.9 1.5 15.5 1 16.7 1zM20.8 17.2c-.5 1.2-.8 1.8-1.5 2.8-1 1.4-2.4 3-4.1 3-1.5 0-1.9-1-4-1s-2.5 1-4 1c-1.7 0-3-1.5-4-3C.4 15.8 1 9.7 5.3 7.5c1.5-.8 3.1-.8 4.6-.2 1.1.4 1.8.5 2.5.5s1.7-.4 3-.7c1.6-.3 3.4.3 4.6 1.7-4 2.2-3.4 6.9.8 8.4z" />
      ) : (
        <>
          <path d="M8 9c-1-6 1-8 4-8s5 2 4 8l3 8-3 4H8l-3-4z" />
          <ellipse cx="12" cy="15" rx="4" ry="5" fill="var(--h-bg)" />
          <circle cx="10" cy="7" r="1" fill="var(--h-bg)" />
          <circle cx="14" cy="7" r="1" fill="var(--h-bg)" />
          <path d="m10 9 2 2 2-2zM4 20l5-1v3H3zm11-1 5 1 1 2h-6z" />
        </>
      )}
    </svg>
  );
}

function InstallerDownloads(): ReactNode {
  const t = useTranslator();
  const locale = useLocale();
  const [os, setOS] = useState<InstallerOS | null>(null);
  const [macArch, setMacArch] = useState("aarch64");
  const [terminalOS, setTerminalOS] = useState<"unix" | "windows" | null>(null);
  useEffect(() => {
    const ua = navigator.userAgent;
    if (
      !/Android|iPhone|iPad/.test(ua) &&
      !(navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
    ) {
      if (/Windows/.test(ua)) {
        setOS("windows");
      } else if (/Mac/.test(ua)) {
        setOS("macos");
      } else if (/Linux/.test(ua)) {
        setOS("linux");
      }
    }
  }, []);
  const name =
    os === "macos" ? "macOS" : os === "windows" ? "Windows" : "Linux";
  const asset = `suzent-installer-${os}-${os === "macos" ? macArch : "x86_64"}${os === "windows" ? ".exe" : ""}`;
  const activeTerminal = terminalOS ?? (os === "windows" ? "windows" : "unix");
  const cmd = activeTerminal === "windows" ? WIN_CMD : UNIX_CMD;
  return (
    <section
      id="download"
      className={styles.installCompact}
      aria-label={t({
        id: "homepage.download.button",
        message: "Download installer",
      })}
    >
      {os ? (
        <div className={styles.downloadAction}>
          <a
            className={styles.downloadPrimary}
            href={`https://github.com/cyzus/suzent/releases/latest/download/${asset}`}
          >
            <OSIcon os={os} />
            <span>
              {t({
                id: `homepage.download.for.${os}`,
                message: `Download for ${name}`,
              })}
            </span>
          </a>
        </div>
      ) : (
        <p className={styles.platformPrompt}>
          {t({
            id: "homepage.download.desktop",
            message: "Choose your desktop platform",
          })}
        </p>
      )}
      {os === "macos" && (
        <button
          className={styles.macAlternative}
          onClick={() =>
            setMacArch(macArch === "aarch64" ? "x86_64" : "aarch64")
          }
        >
          <span className={styles.selectedProcessor}>
            {macArch === "aarch64" ? "Apple Silicon" : "Intel"} ·{" "}
          </span>
          {t({
            id:
              macArch === "aarch64"
                ? "homepage.download.intel"
                : "homepage.download.apple",
            message:
              macArch === "aarch64" ? "Intel Mac? ↗" : "Apple Silicon? ↗",
          })}
        </button>
      )}
      {os && (
        <p className={styles.downloadInstruction}>
          <Link href={localePath("/docs/getting-started/quickstart", locale)}>
            {t({ id: "homepage.download.help", message: "Setup guide ↗" })}
          </Link>
        </p>
      )}
      <select
        className={styles.systemSelect}
        aria-label={t({
          id: "homepage.download.system",
          message: "Operating system",
        })}
        value={os ?? ""}
        onChange={(e) => setOS(e.target.value as InstallerOS)}
      >
        <option value="" disabled>
          {t({ id: "homepage.download.choose", message: "CHOOSE YOUR SYSTEM" })}
        </option>
        <option value="macos">macOS</option>
        <option value="windows">Windows</option>
        <option value="linux">Linux</option>
      </select>
      {os && (
        <div className={styles.terminalAlternative}>
          <div className={styles.terminalHeader}>
            <p className={styles.terminalLabel}>
              {t({
                id: "homepage.download.terminal",
                message: "Or install via terminal",
              })}
            </p>
            <div
              className={styles.terminalSwitch}
              data-system={activeTerminal}
              role="group"
              aria-label={t({
                id: "homepage.download.system",
                message: "Operating system",
              })}
            >
              <button
                type="button"
                aria-pressed={activeTerminal === "unix"}
                onClick={() => setTerminalOS("unix")}
              >
                macOS / Linux
              </button>
              <button
                type="button"
                aria-pressed={activeTerminal === "windows"}
                onClick={() => setTerminalOS("windows")}
              >
                Windows
              </button>
            </div>
          </div>
          <div className={styles.cmdRow}>
            <pre className={styles.cmdText}>{cmd}</pre>
            <CopyButton text={cmd} />
          </div>
          <div className={styles.cmdRow}>
            <pre className={styles.cmdText}>suzent start</pre>
            <CopyButton text="suzent start" />
          </div>
        </div>
      )}
    </section>
  );
}

// ─── Hero ─────────────────────────────────────────────────────────────────────

function HomepageHeader(): ReactNode {
  const locale = useLocale();
  const translate = useTranslator();
  const [orbPointer, setOrbPointer] = useState<DotFieldPointer>({
    x: 0,
    y: 0,
    active: false,
  });
  const heroOrbRef = useRef<HTMLDivElement>(null);

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

  return (
    <header className={styles.heroBanner}>
      <div className={styles.heroInner}>
        <div className={styles.heroCopy}>
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

          <p className={styles.heroTagline}>
            {translate({
              id: "homepage.hero.description",
              message: "Your agent. Beyond any model.",
            })}
          </p>
          <InstallerDownloads />
        </div>
        <div className={styles.heroOrb} ref={heroOrbRef}>
          <DotCube pointer={orbPointer} />
          <HeroArt pointer={orbPointer} />
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
        <div className={styles.exploreMore}>
          <Link href={localePath("/docs/getting-started/intro", locale)}>
            {translate({
              id: "homepage.explore.docs",
              message: "Explore the documentation ↗",
            })}
          </Link>
          <Link href={localePath("/sovereign", locale)}>
            {translate({
              id: "homepage.explore.sovereign",
              message: "Read the sovereignty protocol ↗",
            })}
          </Link>
        </div>
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
