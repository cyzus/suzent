---
sidebar_position: 6
title: Browser
description: Let the agent browse inside the Suzent app where you can watch it, in a browser of its own, or in your Chrome or Edge with your logins through the Suzent extension.
---

# Browser

The agent can open web pages, click, type, and read what's on screen. It can do
this in a browser of its own, or in your everyday Chrome or Edge, where you're
already signed in. Choose in **Settings → Browser**.

## Option 1: The built-in browser (default)

In the Suzent desktop app the agent browses inside the app. Open the
**Browser** panel in the right sidebar to see the page it is working on. The
page is live: you can scroll, click, type, or sign in yourself, and the agent
carries on from there. With the panel closed the agent keeps working out of
sight.

The built-in browser keeps its own logins, separate from the app and from your
everyday browser. It can only open web pages, never files on your computer,
and it never gets your camera, microphone, location or downloads.

When the app is closed, for example while Suzent runs as a background service
or you use the web UI, the agent uses its own browser (Option 2) instead.

## Option 2: The agent's own browser

Select **Launch a managed browser** in **Settings → Browser** to always use a
separate, invisible browser. It uses Chrome or Edge if one is installed, and
otherwise downloads Chromium the first time the agent needs it. You can:

- choose **Chromium**, **Chrome**, or **Edge** (browsers that aren't installed
  are greyed out; click **Refresh** after installing one);
- turn on **Remember browser logins** so sites stay signed in between sessions;
- turn on **Show browser window** to watch it work, or to sign in or solve a
  verification step yourself.

These options also apply when the built-in browser falls back to this one.
Changes apply on the agent's next browser action. Its saved logins are kept in
`~/.suzent/browser_profile` and never mixed with your own browser profile.

## Option 3: Your own browser, with the Suzent extension

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

**To stop,** click **Forget connection** in Settings, or Disconnect in the
extension's popup. Your tabs stay open.

If your organization blocks the Web Store, expand **Manual installation**,
click **Download extension**, unzip it into a permanent folder, and load it
from your browser's Extensions page with Developer mode on (**Load unpacked**).

## Watching what the agent does

When the agent uses your own browser, Suzent shows the connection status and the
selected tab's title. Click **Show tab** to bring that tab forward, or turn on
**Live preview** to watch inside Suzent. For the agent's own browser, the
preview is on by default. The built-in browser needs no preview: the Browser
panel shows the page itself.

Both you and the agent can use the browser at the same time, so avoid clicking
around in the selected tab while the agent is in the middle of a step.

## Several steps at once, and running code on a page

To save time, the agent can do several known steps in one go, such as filling in
every field of a form and pressing Send. You see each step in the chat as usual,
and it stops at the first step that fails.

For jobs the normal clicks and typing can't do well, such as collecting a long
table from a page, the agent can ask to run its own code on that page. That
code runs with your sign-in on that site, so it can read or change anything you
could there. Suzent always asks first and shows you the code and the site. You
can allow it once, for this chat, or always for that site.

To see or change your choices, open **Settings → Browser → Sites that can run
code**. You can allow a site, block one so the agent is never allowed to run
code there, or remove a choice so it asks again. In Full Access mode the agent
doesn't ask, but blocked sites stay blocked.

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
| `SUZENT_BROWSER_CONNECTION_MODE` | `desktop` (default), `managed`, `extension`, or `existing` for the direct connection above |

Environment variables override the desktop settings.
