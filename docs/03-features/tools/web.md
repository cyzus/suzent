---
sidebar_position: 5
title: Web search & pages
description: How the agent searches the web and reads pages, how to use your own SearXNG instance, and where to follow along.
---

# Web search & pages

The agent can look things up on the web and read whole pages. Both are in the
**Web** group of the tool picker. Web search is on by default; reading pages
is not, but the agent switches it on when a task needs it (or tick it yourself).
To click, type, or use sites you're signed in to, the agent drives a browser
instead; see [Browser](./browser.md).

## Web search

Search works out of the box with DuckDuckGo. The agent can narrow a search in a
few ways:

| Option | Choices |
|---|---|
| Kind of result | general web, news, images, or videos |
| Time range | past day, week, month, or year |
| Number of results | 10 by default, up to 20 |

Each result comes back with its title, link, and a short snippet.

### Use your own SearXNG instance

For more private or more reliable results, run your own
[SearXNG](https://docs.searxng.org/) instance and point Suzent at it:

1. Make sure the instance allows JSON output (add `json` to `search.formats` in
   its `settings.yml`).
2. Set `SEARXNG_BASE_URL` to its address, for example
   `SEARXNG_BASE_URL=http://localhost:8080`, in the `.env` file in your Suzent
   folder (see [Configuration](../../07-reference/configuration.md#environment-variables)).
3. Restart Suzent.

If the instance can't be reached, returns an error status, refuses JSON with a
"403 Forbidden", or answers with something other than JSON (such as a web
page), Suzent quietly falls back to DuckDuckGo for that search. If results
keep looking like DuckDuckGo's, check step 1.

## Reading a page

Give the agent a link, or let it pick one from search results, and it reads
the page as plain text with headings, lists, and links kept. This works for
public pages only: it doesn't use your logins, so for your email or an
internal site use [your own browser](./browser.md#option-2-your-own-browser-with-the-suzent-extension).

Very long pages are cut short in the agent's view, at about 30,000
characters. The full text is saved to a file the agent can open if it needs
the rest. These files are deleted after 24 hours.

## Sources in answers

Search results and pages the agent has read become sources it can cite.
Citations appear as small badges in the answer, with a list of sources at the
end of the message.

## Following along in the Web tab

The **Web** tab in the chat's side panel shows the agent's web activity. When
the agent is using a browser, you see it live. Click **History** (the counter
in the top right) to list every search and page from this chat, and click one
to see the search results or the page text the agent read. To go back to the
browser, click the title on the left (it shows **Return to Browser** when you
hover over it).
