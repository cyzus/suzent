---
title: Suzent Mobile Privacy Policy
description: How the Suzent mobile app for iPhone, iPad and Android handles your messages, attachments, and pairing credentials.
---

# Suzent Mobile Privacy Policy

Last updated: October 31, 2026

Publisher: Yizhou Chi  
Privacy contact: [support@suzent.com](mailto:support@suzent.com)

## Scope

This policy covers the Suzent mobile app for iPhone, iPad, and Android. The app is a companion client for a Suzent desktop app that you run yourself. It is not a standalone AI service, and the publisher does not operate a server that the app connects to.

## Information the app processes

When you use the app, it processes:

- Messages you write and the replies, tool activity, and conversation history shown from your Suzent desktop.
- Photos, camera captures, and files you choose to attach to a message.
- The pairing invitation you scan or paste, including your desktop's network addresses and certificate details.
- Your model choice for each conversation.

The camera is used only to scan a pairing QR code or to take a photo you choose to send. The app reads only the photos and files you pick.

## Where information goes

The app sends messages and attachments directly to the Suzent desktop you paired with, over an encrypted HTTPS connection. The publisher does not receive, store, or have access to this information.

Your Suzent desktop may keep this information in its conversations, memory, and logs, and may send relevant parts to the AI model provider or other services you have configured, such as OpenAI, Anthropic, Google, or a local model. Those providers handle the information under their own terms and privacy policies. Review your desktop's model and service settings before sharing sensitive information.

The app contains no advertising, analytics, or tracking, and it does not sell or share information with data brokers.

## Information stored on your device

- The pairing credential is kept in the iOS Keychain (this device only) or, on Android, encrypted with a key held in the Android Keystore.
- Model choices are kept in the app's local settings.
- Attachments are copied to temporary storage while you prepare a message and removed after sending or discarding them.
- The offline demo keeps its sample conversations on the device. It does not connect to any server.

## Retention and deletion

**Forget connection** in the app's settings deletes the pairing credential. Resetting the demo deletes its sample data. Uninstalling the app removes its other stored data. On iPhone and iPad, the pairing credential can remain in the Keychain after you uninstall and be used again if you reinstall, so choose **Forget connection** before uninstalling. Revoking the phone under **Paired phones** in desktop **Settings → Devices → Mobile access** stops it from connecting again.

Conversations kept by your Suzent desktop, and copies held by model providers, are managed on the desktop and in your provider accounts. Removing the app does not delete them.

## Children

The app is not directed at children under 13.

## Questions and changes

Contact the publisher using the privacy contact above for questions about this policy. Do not include pairing invitations or credentials in public issue reports.

Changes to this policy will be published on this page with an updated date. Project source and support are available on [GitHub](https://github.com/cyzus/suzent).
