"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { SiteNav } from "../site-nav";
import { useLocale, localePath } from "../locale";
import {
  GITHUB_LATEST,
  MIRROR_RELEASES,
  useDownloadSource,
} from "../../lib/download-source";
import downloads from "../../../content/downloads.json";
import styles from "./downloads.module.css";

const COPY = {
  en: {
    title: "One agent. Every device.",
    eyebrow: "DOWNLOAD SUZENT",
    intro:
      "Choose your platform. Official stores, standalone installers, and beta releases—all in one place.",
    stable: "Stable release",
    recommended: "Recommended",
    standalone: "Standalone installer",
    ios: "Get the stable app, or try upcoming features in the TestFlight beta.",
    windows: "Install from Microsoft Store, or use the standalone installer.",
    mac: "Choose the installer for your Mac’s processor.",
    linux: "Download the desktop installer for x86_64 Linux.",
    android: "Install directly using the Android APK.",
    appStore: "Download on the App Store",
    beta: "Join TestFlight · Beta",
    store: "Get from Microsoft Store",
    windowsInstaller: "Download Windows installer · x86_64",
    linuxInstaller: "Download Linux installer · x86_64",
    apk: "Download Android APK",
    terminal: "Prefer the terminal?",
    terminalBody:
      "The homepage includes installation commands for macOS, Linux, and Windows.",
    terminalLink: "Command-line installation",
    guide: "Read the setup guide",
  },
  "zh-Hans": {
    title: "一个智能体，随你到每台设备。",
    eyebrow: "下载 SUZENT",
    intro: "选择你的平台。官方商店、独立安装包和测试版，都在这里。",
    stable: "正式版",
    recommended: "推荐",
    standalone: "独立安装包",
    ios: "下载正式版，或通过 TestFlight 测试版体验新功能。",
    windows: "通过 Microsoft Store 安装，也可以使用独立安装包。",
    mac: "根据 Mac 的芯片类型选择安装包。",
    linux: "下载适用于 x86_64 Linux 的桌面安装程序。",
    android: "通过 APK 直接安装 Android 应用。",
    appStore: "从 App Store 下载",
    beta: "加入 TestFlight · 测试版",
    store: "从 Microsoft Store 获取",
    windowsInstaller: "下载 Windows 安装包 · x86_64",
    linuxInstaller: "下载 Linux 安装包 · x86_64",
    apk: "下载 Android APK",
    terminal: "习惯使用终端？",
    terminalBody: "首页保留了 macOS、Linux 和 Windows 的命令行安装方式。",
    terminalLink: "命令行安装",
    guide: "阅读安装指南",
  },
};

export default function Downloads(): ReactNode {
  const locale = useLocale();
  const copy = COPY[locale];
  const { mirrorTag } = useDownloadSource();
  const base = mirrorTag ? `${MIRROR_RELEASES}/${mirrorTag}` : GITHUB_LATEST;
  const platforms = [
    {
      title: "iOS / iPadOS",
      tag: copy.stable,
      description: copy.ios,
      links: [
        { label: copy.appStore, href: downloads.appStore },
        { label: copy.beta, href: downloads.testflight },
      ],
    },
    {
      title: "Windows",
      tag: copy.recommended,
      description: copy.windows,
      links: [
        { label: copy.store, href: downloads.microsoftStore },
        {
          label: copy.windowsInstaller,
          href: `${base}/suzent-installer-windows-x86_64.exe`,
        },
      ],
    },
    {
      title: "macOS",
      tag: copy.standalone,
      description: copy.mac,
      links: [
        {
          label: "Apple Silicon · .dmg",
          href: `${base}/suzent-installer-macos-aarch64.dmg`,
        },
        {
          label: "Intel · .dmg",
          href: `${base}/suzent-installer-macos-x86_64.dmg`,
        },
      ],
    },
    {
      title: "Linux",
      tag: copy.standalone,
      description: copy.linux,
      links: [
        {
          label: copy.linuxInstaller,
          href: `${base}/suzent-installer-linux-x86_64`,
        },
      ],
    },
    {
      title: "Android",
      tag: "APK",
      description: copy.android,
      links: [{ label: copy.apk, href: "/download/android/" }],
    },
  ];
  return (
    <>
      <SiteNav />
      <main className={styles.page}>
        <header className={styles.header}>
          <p className={styles.eyebrow}>{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p>{copy.intro}</p>
        </header>
        <div className={styles.grid}>
          {platforms.map((platform) => (
            <section key={platform.title} className={styles.card}>
              <div className={styles.cardHeading}>
                <h2>{platform.title}</h2>
                <span>{platform.tag}</span>
              </div>
              <p>{platform.description}</p>
              <div className={styles.actions}>
                {platform.links.map((link, index) => (
                  <a
                    key={link.href}
                    href={link.href}
                    className={index === 0 ? styles.primary : styles.secondary}
                  >
                    {link.label}
                    <span aria-hidden="true"> ↗</span>
                  </a>
                ))}
              </div>
            </section>
          ))}
          <section className={styles.card}>
            <h2>{copy.terminal}</h2>
            <p>{copy.terminalBody}</p>
            <div className={styles.actions}>
              <Link
                className={styles.secondary}
                href={localePath("/#terminal", locale)}
              >
                {copy.terminalLink} ↗
              </Link>
              <Link
                className={styles.secondary}
                href={localePath("/docs/getting-started/quickstart", locale)}
              >
                {copy.guide} ↗
              </Link>
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
