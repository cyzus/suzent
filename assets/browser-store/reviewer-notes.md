# Reviewer notes and permission explanations

Draft: verify against the exact release submitted for review.

## Single purpose

Connect the user's locally running Suzent personal AI agent to their existing browser's web tabs, enabling user-requested browsing tasks and an in-app preview.

## Permissions

| Permission/access | Explanation |
| --- | --- |
| `debugger` | Attach to the selected web tab to inspect page elements, perform clicks and keyboard input, and stream preview frames to the paired local Suzent application. The connection detaches when revoked; it does not close the user's tabs. |
| `tabs` | List eligible tabs with their titles and URLs so the user/agent can select the intended page; open and navigate tabs for requested tasks. |
| `storage` | Save the pairing credential and local backend address in extension local storage, enabling reconnection. |
| `alarms` | Retry the connection to the paired local application when it becomes available again. |
| `nativeMessaging` | Contact the local `com.suzent.browser` helper to discover Suzent's current loopback port after app restarts. The helper reads a local runtime port file; it does not control the browser. |
| Content script on `http://127.0.0.1/*` | Handle the local `/browser/extension/connect` pairing page. The script checks the exact path and token format. The backend port varies by installation. |

## Executable logic disclosure requiring review

The packaged service worker accepts a limited set of CDP methods from the paired localhost backend. This includes `Runtime.evaluate`: Suzent supplies JavaScript expressions for snapshots and element validation, executed in an isolated world in the selected page. The Python backend currently contains those expressions. The extension does not fetch third-party JavaScript libraries, but that fact alone is not a sufficient answer to the stores' remote-code questions. Explain this architecture accurately and assess the applicable policy before submitting. Store acceptance has not been verified; moving fixed scripts into the extension may be needed.

## Reproduction instructions

1. Install a released Suzent build containing PR #197's extension bridge. Publisher must supply an exact release/download link and OS setup instructions before submission.
2. Run Suzent on the same computer. Install the submitted extension in Chrome or Edge.
3. Open Suzent Settings → Browser, choose “Use my browser (extension),” and click “Pair browser.” If a different default browser opens, paste the private pairing link into the browser with this extension. Links expire in five minutes.
4. Confirm that Settings shows Connected. Open a non-sensitive test web page.
5. With a model configured in Suzent, ask it to list tabs, select the test tab, read the page, and open another page. Supply reviewers with a usable model setup or a separate test arrangement; do not place production credentials in this repository.
6. Open Suzent's browser preview and confirm it follows the selected tab. The browser may display its standard debugger notification.
7. Disconnect from the extension popup or use Disconnect and forget in Suzent. Confirm browser tabs remain open and further agent actions require a connection.
8. Pair again, restart Suzent, and verify reconnection. Native helper registration is per user. If enterprise policy blocks the helper, pairing may be needed again when the backend port changes.

Private tabs, browser-internal pages, embedded-frame interactions, uploads/download management, select-option filling, and complex keyboard layouts are outside this version's scope. There is no extension-specific account or subscription. A working local Suzent app is required.
