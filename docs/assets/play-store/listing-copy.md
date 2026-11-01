# Google Play listing copy

Limits are Play Console's: app name 30 characters, short description 80,
full description 4000, release notes 500 per language. Play has no keyword
field; the title, short description and full description are what search
indexes.

## English (United States) – en-US

App name: Suzent: Personal AI Agent

Short description: Your own AI agent, in your pocket. Runs on your computer, answers to you.

### Full description

Suzent is a personal AI agent that runs on your own computer. It remembers what matters to you, works with your files and apps, and keeps going while you are away. This app puts it in your pocket.

From your phone, you can:

• Catch up fast. Ask "What changed while I was away?" and get a summary built from your notes and projects.
• Plan with context. Suzent remembers your preferences, so a weekend plan already fits how you travel, with sources you can check.
• Stay in control. When Suzent wants to move files or run a command on your computer, you approve or reject it with one tap.
• Let it keep watch. Regent, your always-on agent, flags only what needs you, like a pull request waiting for review or a check-in about to open.
• Run your routines. Check scheduled tasks such as a morning briefing, and send photos and files straight to your agent.

Your data stays yours. Conversations, memory and tools live on your computer, and the app connects to it directly over an encrypted connection: on your Wi-Fi, through Tailscale, or at your own HTTPS address. No accounts, no ads, no tracking.

Getting started: install Suzent on your computer from suzent.com, open Settings → Devices → Mobile access, and scan the QR code. No computer yet? Tap "Try offline demo" to look around with sample conversations.

AI replies use the model provider you configure on your computer; provider charges may apply. Suzent is open source: github.com/cyzus/suzent

### Release notes

<en-US>
• A new offline demo shows a real week with Suzent: project summaries, trip planning, and approving actions on your computer.
• Privacy policy link in Settings and on the connection screen.
• Wider tablet layouts keep conversations at a readable width.
</en-US>

## 中文（简体）– zh-CN

应用名称：Suzent：个人 AI 智能体

简短说明：把你自己的 AI 智能体装进口袋。运行在你的电脑上，只听你的。

### 完整说明

Suzent 是运行在你自己电脑上的个人 AI 智能体。它记得对你重要的事，能操作你的文件和应用，你不在时也能继续工作。这个 App 让你随时带着它。

在手机上，你可以：

• 快速跟上进度。问一句“我不在的时候有什么变化？”，Suzent 会根据你的笔记和项目给出汇总。
• 带着上下文做计划。Suzent 记得你的偏好，周末行程一开始就符合你的出行习惯，并附上可以核对的来源。
• 一切由你掌控。Suzent 想在电脑上移动文件或运行命令时，你一键批准或拒绝。
• 让它替你盯着。常驻智能体 Regent 只提醒需要你处理的事，比如等你审的 PR、即将开放的值机。
• 照常运行你的例行任务。查看晨间简报等定时任务，把照片和文件直接发给智能体。

数据始终属于你。对话、记忆和工具都在你的电脑上，App 通过加密连接直接连到它：同一 Wi-Fi、Tailscale 或你自己的 HTTPS 地址都可以。没有账号，没有广告，没有跟踪。

开始使用：从 suzent.com 在电脑上安装 Suzent，打开“设置 → 设备 → 移动端访问”，扫描二维码即可。还没有电脑端？点“体验离线演示”，用示例对话先看看。

AI 回复使用你在电脑上配置的模型提供商，可能产生提供商费用。Suzent 是开源项目：github.com/cyzus/suzent

### 版本说明

<zh-CN>
• 全新离线演示，带你体验真实的一周：项目汇总、行程规划，以及在手机上批准电脑上的操作。
• 设置和连接页面新增隐私政策链接。
• 平板宽屏下对话保持易读的宽度。
</zh-CN>

## Screenshot captions

Same five screens and captions as the
[App Store kit](../app-store/listing-copy.md#screenshot-captions), captured
from the Android offline demo. `scripts/build_play_store_assets.py` reuses
that caption text.

| # | Phone screen |
| --- | --- |
| 1 | "Plan my Lisbon weekend" reply |
| 2 | "Tidy up my Downloads folder" approval |
| 3 | Sidebar |
| 4 | Connection screen |
| 5 | Regent |

## Store settings

| Field | Value |
| --- | --- |
| App category | Productivity |
| Tags | AI assistant, Productivity, Remote desktop (pick from Play's list) |
| Contact email | support@suzent.com |
| Website | https://suzent.com |
| Privacy policy | https://suzent.com/mobile-privacy |
