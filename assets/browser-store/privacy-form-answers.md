# Privacy form answers — Chrome and Edge

Applies to the current 0.1.0 extension ZIP. Save as draft pending the remote-code review. Privacy policy URL: https://suzent.com/browser-privacy.

## Single purpose

Connect the user's locally running Suzent AI assistant to their existing browser tabs to perform requested browsing tasks and display a preview of the selected tab.

## debugger

Used to attach to the selected web tab, inspect page content and elements, perform browser interactions, and send live preview frames to the paired local Suzent application. The debugger detaches when access is revoked, without closing the user's tabs.

## tabs

Used to list eligible tabs with their titles and URLs, select the intended tab, and open or navigate tabs for browsing tasks. Private/incognito tabs are excluded.

## storage

Used to store the pairing credential and local Suzent backend address in extension local storage so the extension can reconnect to the paired application. Disconnecting and forgetting the pairing removes the extension's saved pairing credentials.

## alarms

Used to periodically reconnect to the previously paired local Suzent application after the browser service worker or application restarts. This supports connection recovery, not tracking or advertising.

## nativeMessaging

Used to contact the com.suzent.browser native messaging helper, which reads Suzent's local runtime port file and returns the loopback endpoint. This lets the extension find Suzent when the app's port changes. The helper does not itself control browser tabs or grant authorization.

## Host/content-script access: http://127.0.0.1/*

Used for the local Suzent pairing page. The content script verifies the /browser/extension/connect path and pairing token format before passing the token to the extension. The local backend port can vary between installations and app launches.

## Remote code — current build

Do not select No for the current build without resolving its backend-supplied JavaScript architecture. For a draft disclosure, select Yes and explain:

The extension receives commands from the user's paired Suzent application over a localhost WebSocket. Some commands contain JavaScript expressions supplied by the local Python backend and executed through chrome.debugger Runtime.evaluate in an isolated world of the selected webpage. These implement page snapshots and element validation. The extension does not download JavaScript libraries from an external CDN. These expressions are not currently bundled inside the extension ZIP.

This describes the implementation; it does not establish store acceptance. Edge's documentation prohibits remotely hosted code in MV3. Chrome describes limited isolated-context exceptions but requires the full functionality to be reviewable. Refactoring fixed scripts into the extension and removing arbitrary expression transport is the clearest route before submission.

## Data categories

Clearly applicable: Website content; Web history (tab URLs and titles, even without the history API); User activity (browsing interactions); Authentication information (pairing credential).

Additional categories to assess for the supported use cases: Personally identifiable information; Personal communications; Financial and payment information; Health information; Location. The extension can capture these when present in selected page text or screenshots and pass them to Suzent/the configured model provider. Do not claim they are excluded unless actual restrictions enforce that. For the current unrestricted page-reading design, declaring all nine categories is the conservative option; this does not imply separate location tracking or financial-data integrations exist.

## Data handling explanation

The extension processes tab titles and URLs, selected webpage content and screenshots, browser interaction commands, and local pairing credentials. Browser information is sent to the paired Suzent application on the same computer. Suzent may retain tool results and conversations and send relevant content to the AI provider configured by the user. The extension has no advertising or analytics SDK. Disconnecting stops further browser access but does not delete information already retained by Suzent or a provider.

## Data-use certifications

Only certify these statements if they match your actual operating practices and the providers used by the released product:

- Data is not sold or transferred outside the permitted use cases.
- Data is not used or transferred for purposes unrelated to the extension's single purpose.
- Data is not used or transferred to determine creditworthiness or for lending purposes.

Transfers to a configured AI provider must be disclosed; do not interpret these certifications as permission to omit such transfers or to claim everything remains local. The source code alone cannot establish the publisher's or providers' business practices.

## Privacy policy URL

Enter https://suzent.com/browser-privacy. Publisher: Yizhou Chi. Privacy contact: cyzus@outlook.com.

## Sources

https://developer.chrome.com/docs/webstore/cws-dashboard-privacy
https://developer.chrome.com/docs/webstore/program-policies/mv3-requirements
https://learn.microsoft.com/en-us/microsoft-edge/extensions/publish/publish-extension#step-6-enter-privacy-information
