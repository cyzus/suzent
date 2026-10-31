# Suzent iOS App Store submission kit

Prepared 2026-10-31 for mobile-v0.5.2 (build 9). Mirrors the
[browser store kit](../browser-store/README.md): listing copy lives here,
generated images go to `store-upload/app-store/` and stay out of Git.

## Upload map

| App Store Connect field | Source | Notes |
| --- | --- | --- |
| Name, subtitle, promotional text, keywords, description, What's New | `listing-copy.md` | English (U.S.) and Simplified Chinese |
| iPhone screenshots | `store-upload/app-store/<locale>/iphone-0N.png` | 1206 × 2622 or 1179 × 2556, required |
| iPad screenshots | `store-upload/app-store/<locale>/ipad-0N.png` | 2064 × 2752, required because the app supports iPad |
| Screenshot captions | `listing-copy.md` → Screenshot captions | Same order on iPhone and iPad |
| Privacy Policy URL | https://suzent.com/mobile-privacy | Source: `website/content/mobile-privacy.md` |
| Support URL | https://github.com/cyzus/suzent/issues | Same as the browser extension |
| Marketing URL | https://suzent.com | |
| App Privacy | Data Not Collected, no tracking | Matches `apps/ios/Suzent/PrivacyInfo.xcprivacy` |
| Export compliance | Not asked from build 8 onward | `ITSAppUsesNonExemptEncryption = NO`; only HTTPS, CryptoKit and Security |
| App Review notes | [Store review demonstration](../../08-developing/contributing/mobile-releases.md#store-review-demonstration) | Add the physical-device pairing video link |

## Screenshots

Capture the offline demo so no real conversations, hosts or tokens appear.
Screens 1–3 come straight from the demo; screens 4 and 5 need the
connection screen and a paired Settings page from a test desktop.

1. Boot the "iPhone 17 Pro" and "iPad Pro 13-inch (M5)" simulators, install a
   Release build, and choose **Try offline demo**.
2. Use light appearance and English or Chinese to match the locale.
3. Save each capture with `xcrun simctl io <device> screenshot <file>.png`.
4. Add the caption from `listing-copy.md` above the device frame. Store
   screenshots must show the real app; captions and framing are allowed.

## Before submitting

- Select build 9 (0.5.2) or later; earlier builds lack the in-app privacy link.
- Leave China mainland out of availability until an ICP filing exists.
- Declare EU trader status under App Store Regulations and Permits.
- Answer the age rating questionnaire as described in the submission guide;
  in-app links open in a Safari view, so Unrestricted Web Access is Yes (16+).
