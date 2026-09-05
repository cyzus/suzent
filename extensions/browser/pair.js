if (
  location.pathname === "/browser/extension/connect" &&
  /^[A-Za-z0-9_-]{43}$/.test(location.hash.slice(1))
) {
  const token = location.hash.slice(1);
  history.replaceState(null, "", location.pathname);
  chrome.runtime.sendMessage(
    { type: "pair", origin: location.origin, token },
    (result) => {
      document.body.textContent = chrome.i18n.getMessage(
        result?.ok ? "paired" : "failed",
      );
    },
  );
}
