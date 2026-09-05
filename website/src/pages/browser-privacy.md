---
title: Suzent Browser Privacy Policy
description: How the Suzent Browser extension processes browser information, pairs with the local app, and lets you control access.
---

# Suzent Browser Privacy Policy

Last updated: September 6, 2026

Publisher: Yizhou Chi  
Privacy contact: [cyzus@outlook.com](mailto:cyzus@outlook.com)

## Scope

This policy covers the Suzent Browser extension for Chrome and Microsoft Edge and its connection to the Suzent application running on your computer. The extension is a companion to Suzent, not a standalone AI service.

## Information the extension processes

When paired with Suzent, the extension can list eligible tabs and process their titles and URLs. For the selected tab, it can read webpage content and element information, capture screenshots or live preview frames, and perform browser interactions such as navigation, clicks, and text entry.

Page content, screenshots, URLs, and text entered during a task may contain personal or sensitive information, including information visible in signed-in accounts. The extension does not filter every category of sensitive information out of page content or screenshots. Consider the information on a page before asking Suzent to work with it.

The extension uses your existing browser session. It does not copy your browser's cookie database to Suzent. Private/incognito tabs and browser-internal pages are excluded from the extension's supported browsing operations.

## Pairing and local storage

The extension stores a pairing credential and the local backend address in browser extension local storage. Suzent stores a hash of that credential and the authorized extension origin on your computer. These are used to authenticate the connection and reconnect to the paired app.

Pairing also registers a per-user native messaging helper. The helper reads Suzent's local runtime port file so the extension can locate the app after restarts. It does not itself control browser tabs or grant browser-access authorization.

## Where browser information goes

The extension sends browser information to the paired Suzent application over a loopback connection on the same computer. The extension itself does not include an advertising or analytics service.

Local communication between the extension and Suzent does **not** mean all subsequent processing stays on your computer. Depending on your configuration, Suzent may retain browser information in conversations, tool results, logs, or other app storage, and may send relevant information to your configured AI model provider or other services used for your task.

Those providers' processing and retention practices are governed by their own terms, privacy policies, and your account settings. Review your Suzent configuration and provider settings before working with sensitive information.

## How information is used

The extension processes browser information to provide its connection, browsing actions, and preview functionality. Its pairing credential and local address support authentication and connection recovery. The extension does not implement advertising profiles, data-sale functionality, or creditworthiness scoring.

## Retention and deletion

Pairing information remains in extension local storage until it is removed, such as by forgetting the pairing or uninstalling the extension. The app maintains its local authorization record until it is revoked or deleted.

Browser content retained by Suzent or a configured provider is separate from the extension's pairing information. There is no single extension-wide retention period for those copies: retention depends on the app's storage, task configuration, and provider practices. Use the applicable app and provider data controls to manage or delete retained information.

## Your controls

You can stop extension access by disconnecting in the extension popup, choosing **Disconnect and forget** in Suzent's Browser settings, or uninstalling the extension. Disconnecting leaves your browser tabs open.

Stopping the connection does not automatically erase information already retained by Suzent or an external provider. Revoking pairing may leave the discovery-only native messaging helper registered on your computer; it cannot authorize browser control without a valid pairing.

## Questions and changes

Contact the publisher using the privacy contact above for questions about this policy. Do not include passwords, pairing tokens, or sensitive webpage content in public issue reports.

Changes to this policy will be published on this page with an updated date. Project source and general support are available on [GitHub](https://github.com/cyzus/suzent).
