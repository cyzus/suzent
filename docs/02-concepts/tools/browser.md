---
sidebar_position: 3
title: Browser
description: Let the agent browse in its own browser, or in your Chrome or Edge with your logins through the Suzent extension.
---

# Browser

The agent can open web pages, click, type, and read what's on screen. It can do
this in a browser of its own, or in your everyday Chrome or Edge, where you're
already signed in. Choose in **Settings → Browser**.

## Option 1: The agent's own browser (default)

By default the agent uses a separate, invisible Chromium browser that has
nothing to do with your personal browsing. In **Settings → Browser** you can:

- choose **Chromium**, **Chrome**, or **Edge** (browsers that aren't installed
  are greyed out; click **Check installed browsers** after installing one);
- turn on **Remember browser logins** so sites stay signed in between sessions;
- turn on **Show browser window** to watch it work, or to sign in or solve a
  verification step yourself.

Changes apply on the agent's next browser action. Its saved logins are kept in
`~/.suzent/browser_profile` and never mixed with your own browser profile.

## Option 2: Your own browser, with the Suzent extension

Use this when the agent needs your tabs and logins, such as your email or an
internal site.

1. In **Settings → Browser**, select **Use my browser (extension)**.
2. Click **Open Chrome Web Store** or **Open Edge Add-ons** and install
   [Suzent Browser](https://chromewebstore.google.com/detail/suzent-browser/mjfjhclnoepglnjjmheollfpbngjebno)
   ([Edge version](https://microsoftedge.microsoft.com/addons/detail/suzent-browser/hobapppkcjggdhbbpnokgcoiddailnib))
   in the browser profile you want the agent to use.
3. Back in Suzent, click **Pair browser**. A pairing page opens in your default
   browser. If you installed the extension in a different browser, copy the
   pairing link shown in Suzent into that browser instead. Links expire after
   five minutes.
4. Settings shows **Browser extension connected**. Now ask the agent to list
   your tabs and pick one, or to open a new page.

You only pair once per browser profile. Pairing a different profile replaces
the previous one.

**What the extension can and can't do.** It works only on normal web pages,
never on private or incognito tabs, and only on the one tab the agent has
selected. It never reads what you've typed into form fields. Chrome or Edge
shows a banner while the agent is attached; closing that banner disconnects it.

**To stop,** click **Disconnect and forget** in Settings, or Disconnect in the
extension's popup. Your tabs stay open.

If your organization blocks the Web Store, expand **Setup help & options**,
click **Download extension**, unzip it into a permanent folder, and load it
from your browser's Extensions page with Developer mode on (**Load unpacked**).

## Watching what the agent does

When the agent uses your own browser, Suzent shows the connection status and the
selected tab's title. Click **Show tab** to bring that tab forward, or turn on
**Live preview** to watch inside Suzent. For the agent's own browser, the
preview is on by default.

Both you and the agent can use the browser at the same time, so avoid clicking
around in the selected tab while the agent is in the middle of a step.

## Advanced: direct connection

If you can't use the extension, Suzent can attach to Chrome or Edge through its
remote debugging setting instead.

1. In Chrome open `chrome://inspect/#remote-debugging`, or in Edge open
   `edge://inspect` and choose **Remote debugging**. Turn remote debugging on.
2. In **Settings → Browser**, select **Direct connection (advanced)** and choose
   Chrome or Edge.
3. Approve the browser's connection prompt when it appears.

Suzent must run on the same computer as the browser. It starts in a new blank
tab so it doesn't navigate away from your work, and your browser stays open
when Suzent closes.

## Running Suzent from the command line

Without the desktop app, set the browser options as environment variables
before starting Suzent:

| Variable | Values |
|---|---|
| `SUZENT_BROWSER_CHANNEL` | `chromium` (default), `chrome`, or `msedge` |
| `SUZENT_BROWSER_PERSISTENT` | `true` to remember logins |
| `SUZENT_BROWSER_HEADLESS` | `false` to show the window |
| `SUZENT_BROWSER_CONNECTION_MODE` | `existing` for the direct connection above |

Environment variables override the desktop settings.
