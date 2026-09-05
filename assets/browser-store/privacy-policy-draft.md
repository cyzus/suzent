# Suzent Browser — privacy policy draft

**Publisher action required:** replace the bracketed fields, verify the statements against the release and your operating practices, and publish at a stable public URL before submitting. This file is not yet a published privacy policy.

Effective date: [publication date]

Publisher: [legal publisher name]

Privacy contact: [contact email or contact page]

## What the extension does

Suzent Browser connects your browser to the Suzent application running on your computer. When paired, Suzent can list eligible browser tabs, read selected page content, capture preview frames, and interact with webpages for browsing tasks.

## Information processed

The extension can process tab titles and URLs, selected webpage text and structure, screenshots or preview frames, and information supplied for clicks and text entry. Webpage content and screenshots may contain personal or sensitive information, including content visible in signed-in accounts. The extension operates in your existing browser session; it does not need to copy your browser's cookie database to Suzent.

Pairing credentials and the local backend address are stored in extension local storage. Suzent stores a hash of the pairing credential and the authorized extension origin locally. A per-user native messaging helper reads Suzent's runtime port file to locate the app after restarts.

## Where information goes

The extension sends browser information to the paired Suzent backend over a loopback connection on your computer. This does not mean all subsequent processing stays on your computer. Suzent may include browser information in conversations, tool results, logs or other configured app storage, and may send content to the AI model provider you configure. Retention and onward processing depend on Suzent's configuration and the selected provider's practices. Review those settings and provider policies before using the extension on sensitive pages.

The extension's code does not include an advertising or analytics service. Its browser data transfer is used to provide the connection and browsing functionality described above.

## Your controls

You can disconnect from the extension popup, revoke pairing with Disconnect and forget in Suzent, or uninstall the extension. These actions stop future extension access but do not automatically delete information already retained by Suzent or an AI provider. Use the app's and provider's available data controls for retained information.

The native messaging helper may remain registered after pairing is revoked. It only discovers the local app endpoint; it cannot authorize browser control on its own. Private/incognito tabs are excluded by the extension.

## Contact and updates

For questions, contact [privacy contact]. Material changes will be reflected in the policy at [public privacy policy URL].
