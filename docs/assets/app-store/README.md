# Suzent iOS App Store submission kit

Prepared 2026-10-31 for mobile-v0.5.3; screenshots recaptured 2026-11-06 from main after mobile-v0.6.2. Mirrors the
[browser store kit](../browser-store/README.md): listing copy lives here,
generated images go to `store-upload/app-store/` and stay out of Git.

## Upload map

| App Store Connect field | Source | Notes |
| --- | --- | --- |
| Name, subtitle, promotional text, keywords, description, What's New | `listing-copy.md` | English (U.S.) and Simplified Chinese |
| iPhone screenshots | `store-upload/app-store/<locale>/iphone-0N.png` | 1206 × 2622 or 1179 × 2556, required |
| iPad screenshots | `store-upload/app-store/<locale>/ipad-0N.png` | 2064 × 2752, required because the app supports iPad |
| Product page header | `store-upload/app-store/<locale>/header.png` | 3840 × 1646 (21:9) PNG without alpha, Product Page Information → Header and Search Results |
| Search results | `store-upload/app-store/<locale>/search.png` | 3840 × 2560 (3:2) PNG without alpha, same section |
| Screenshot captions | `listing-copy.md` → Screenshot captions | Same order on iPhone and iPad |
| Privacy Policy URL | https://suzent.com/mobile-privacy | Source: `website/content/mobile-privacy.md` |
| Support URL | https://github.com/cyzus/suzent/issues | Same as the browser extension |
| Marketing URL | https://suzent.com | |
| App Privacy | Data Not Collected, no tracking | Matches `apps/ios/Suzent/PrivacyInfo.xcprivacy` |
| Export compliance | Not asked from build 8 onward | `ITSAppUsesNonExemptEncryption = NO`; only HTTPS, CryptoKit and Security |
| App Review notes | [Store review demonstration](../../08-developing/contributing/mobile-releases.md#store-review-demonstration) | Add the physical-device pairing video link |

## Screenshots

All ten screens per locale come from the offline demo, so no real
conversations, hosts or tokens appear.

1. Build the Release app for the simulator and install it on "iPhone 17 Pro"
   and "iPad Pro 13-inch (M5)" with light appearance and
   `xcrun simctl status_bar <device> override --time 9:41 --batteryLevel 100`.
   Sign the build with `CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM=`
   rather than `CODE_SIGNING_ALLOWED=NO`: an unsigned app cannot use the
   keychain and shows "Could not access secure credentials". Reinstall the app
   before switching language so the demo reseeds in that language.
2. Launch with `-AppleLanguages "(en)"` or `"(zh-Hans)"` and choose
   **Try offline demo**. Capture each screen listed in `listing-copy.md` with
   `xcrun simctl io <device> screenshot store-upload/app-store/raw/<locale>/<device>-0N.png`.
3. Run `uv run --no-sync python scripts/build_app_store_assets.py`. It frames the
   captures with their captions into `store-upload/app-store/<locale>/`, at
   1206 × 2622 for iPhone and 2064 × 2752 for iPad, plus the header and
   search results artwork in the Play feature graphic's style: copy on the
   left, iPhone captures 1 and 2 (plan and weekly summary) tilted on the right, the hand-held cube
   between them. The App Store rounds
   screenshot corners, so nothing is drawn along the image edge.

## Before submitting

- Select the 0.5.3 build or later: earlier builds lack the in-app privacy link
  and show the old demo in the screenshots.
- Leave China mainland out of availability until an ICP filing exists.
- Declare EU trader status under App Store Regulations and Permits.
- Answer the age rating questionnaire as described in the submission guide;
  in-app links open in a Safari view, so Unrestricted Web Access is Yes (16+).
