# Suzent Google Play submission kit

Prepared 2026-11-01. Submit the first mobile release after 0.5.3: it drops the
Google code scanner, which the Data safety answers rely on. Mirrors the
[App Store kit](../app-store/README.md): copy and form answers live here,
generated images go to `store-upload/play-store/` and stay out of Git.

## Upload map

| Play Console field | Source | Notes |
| --- | --- | --- |
| App name, short and full description | `listing-copy.md` | English (United States) and Chinese (Simplified) |
| Release notes | `listing-copy.md` → Release notes | Paste with the `<en-US>` / `<zh-CN>` tags |
| App icon | `store-upload/play-store/icon-512.png` | 512 × 512 PNG, built from the launcher artwork |
| Feature graphic | `store-upload/play-store/<locale>/feature-graphic.jpg` | 1024 × 500 JPEG, required |
| Phone screenshots | `store-upload/play-store/<locale>/phone-0N.png` | 1080 × 1920, five per locale (Play needs 2 to 8) |
| App content forms | `console-answers.md` | Data safety, content rating, app access, target audience |
| App bundle | `suzent-X.Y.Z-android.aab` from the matching `mobile-vX.Y.Z` GitHub Release | Never upload a debug or locally built bundle |

## One-time setup

1. Create a Play Console developer account (US$25). An **organization**
   account needs a D-U-N-S number but skips the testing gate below; a
   **personal** account created after November 2023 must run a closed test
   with at least 12 opted-in testers for 14 consecutive days before it can
   apply for production access.
2. Create the app: default language English (United States), App, Free.
   The package name is fixed to `com.suzent.mobile` on the first upload.
3. Switch Play App Signing to your own key. Uploading a bundle does not ask:
   Play enrolls the app with a Google-generated key by default. Before any
   release reaches open testing or production, open **Protected with Play →
   Play Store protection → Manage Play app signing → Change key**, choose to
   provide a copy of your own app signing key, and upload the existing release
   key (the one behind `ANDROID_KEYSTORE_BASE64`) with the PEPK command shown. Play then signs with
   the same key as the GitHub APK, so users can move between the APK and Play
   with an ordinary update. Letting Google generate a key makes the two
   channels incompatible and cannot be undone.
4. Register an upload key. Reusing the release key is simplest; a separate
   upload key is safer if the CI secret ever leaks, because Play can reset it.

## Screenshots

Capture from the offline demo on an Android phone or emulator, so no real
conversations, hosts or tokens appear.

1. Install the release APK from that GitHub Release on a
   1080-wide phone in light mode. Turn on demo mode for a clean status bar:
   `adb shell settings put global sysui_demo_allowed 1` then
   `adb shell am broadcast -a com.android.systemui.demo -e command clock -e hhmm 0941`.
2. Set the phone language to English, open the app and tap
   **Try offline demo**. Capture the five screens listed in `listing-copy.md`
   with `adb exec-out screencap -p > store-upload/play-store/raw/en-US/phone-0N.png`.
   Repeat with the phone set to 简体中文 into `raw/zh-CN/`.
3. Run `uv run --no-sync python scripts/build_play_store_assets.py`. It builds
   the icon and feature graphics, and frames each raw capture it finds.

Do not reuse the iPhone captures: Play rejects screenshots that show another
platform's interface.

## Release path

1. **Internal testing**: upload the AAB, add yourself, and install from Play
   to confirm signing, pairing and the demo. Does not count toward the
   12-tester rule.
2. **Closed testing**: add at least 12 testers (an email list or Google
   Group), roll out, and keep the track running for 14 days. Personal
   accounts only.
3. **Apply for production access** from the dashboard, answering the
   questions about the test.
4. **Production**: create a release with the same AAB, pick countries, and
   send for review. First reviews often take several days.

Each later release is the AAB from the matching `mobile-vX.Y.Z` GitHub
Release, uploaded by hand; CI does not publish to Play.

## Before submitting

- Add an in-app way to report an AI reply (see `console-answers.md` →
  Generative AI apps).
- Record the physical-device pairing video and put its link in the App access
  instructions.
- Leave countries where Play is unavailable out; no ICP filing is needed for
  Play.
