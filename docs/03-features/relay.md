---
sidebar_position: 7.5
title: Your own relay
description: Reach Suzent from your phone on any network, and let services like GitHub call your webhooks, through a relay you deploy yourself.
---

# Your own relay

A relay lets your phone reach Suzent on your computer from any network, and
lets services on the internet, such as GitHub, call your
[webhook tasks](./automation.md#webhooks). You don't need a VPN, port
forwarding, or a fixed IP address.

**You run the relay yourself.** Suzent has no hosted relay, so there is no
Suzent cloud your conversations pass through. You deploy
[suzent-relay](https://github.com/cyzus/suzent-relay) once, for free on
Cloudflare Workers or with Docker on any server, and only your Suzent uses it.
Your agent stays sovereign even when you're away from home.

## How it works

```
Suzent on your computer ──connects out──▶ your relay ◀── Suzent app on your phone
                                              ▲
                                              └── GitHub and other webhook callers
```

Your computer connects out to the relay and keeps that connection open. The
phone and webhook callers send their requests to the relay, which passes them
down that connection. The relay keeps nothing on disk.

- **Phone traffic is end-to-end encrypted.** The pairing QR code carries your
  computer's key, and the phone checks it before sending anything, so the
  relay only passes on data it can't read or change.
- **Only phones and webhooks get through.** Everything else in Suzent stays
  closed to the internet.
- **The relay can read webhook payloads** in transit, as any webhook receiver
  can. That's one more reason to run your own.

## Set it up

1. Deploy suzent-relay. Its
   [README](https://github.com/cyzus/suzent-relay#deploy) walks through each
   option: Cloudflare Workers (free, no server), Docker with automatic HTTPS on
   any server, or behind your own reverse proxy. Note its `https://` address.
   Setting a registration key is recommended, so only your Suzent can use the
   relay.
2. On your computer, open **Settings → Devices → Relay**, enter the **Relay
   address** and **Registration key**, and save. The status changes to
   **Connected**.
3. Turn on the
   [background service](./automation.md#keep-suzent-running-in-the-background)
   so Suzent stays connected after you quit the desktop app. The relay only
   works while Suzent is running on your computer.

## Use it from your phone

Pair the phone by scanning a new QR code; the code now includes the relay. See
[Through your own relay](./mobile.md#through-your-own-relay) on the Mobile app
page.

The phone always tries your computer's direct addresses first, such as your
home Wi-Fi, and only uses the relay when none of them answers. A phone paired
before you set up the relay learns about it the next time it connects to your
computer directly.

## Use it for webhooks

Once the relay is connected, every webhook task shows two URLs: one for this
machine and one through the relay. Give the relay URL to GitHub or any other
service. See [Webhooks through a relay](./automation.md#webhooks-through-a-relay).

## Reset relay addresses

**Reset relay addresses** in the Relay settings issues new addresses. Use it if
another Suzent took over the address, or to cut off phones and webhook callers
that have the old one. Afterwards, pair your phone again and hand out the new
webhook URLs.

## Relay or Tailscale?

Both are fine, and you can use both: the phone tries every address it knows.

- **Tailscale** puts your phone and computer on one private network. It needs
  the Tailscale app on both devices and works only for devices you add.
- **A relay** needs nothing on the phone beyond the Suzent app and also gives
  webhook tasks an address on the internet. You deploy it once.
