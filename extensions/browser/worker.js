let socket;
let connecting = false;
let selected;
let heartbeat;
let frameTimer;
let pendingFrame;
let queue = Promise.resolve();
const attached = new Set();
const allowedMethods = new Set([
  "Page.enable",
  "Page.getFrameTree",
  "Page.createIsolatedWorld",
  "Page.startScreencast",
  "Page.stopScreencast",
  "Page.screencastFrameAck",
  "Page.reload",
  "Page.getNavigationHistory",
  "Page.navigateToHistoryEntry",
  "Runtime.evaluate",
  "Input.dispatchMouseEvent",
  "Input.dispatchKeyEvent",
  "Input.insertText",
]);

export function webUrl(value) {
  if (value === "about:blank") return value;
  const url = new URL(value);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password
  ) {
    throw new Error("Only web pages can be controlled.");
  }
  return url.href;
}

function emit(value) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(value));
}

async function detach() {
  clearTimeout(frameTimer);
  frameTimer = undefined;
  pendingFrame = undefined;
  selected = undefined;
  const ids = [...attached];
  attached.clear();
  await Promise.allSettled(
    ids.map((tabId) => chrome.debugger.detach({ tabId })),
  );
}

async function select(tabId) {
  const tab = await chrome.tabs.get(tabId);
  if (tab.incognito) throw new Error("Private tabs are not supported.");
  webUrl(tab.url);
  if (selected !== tabId) await detach();
  if (!attached.has(tabId)) {
    await chrome.debugger.attach({ tabId }, "1.3");
    attached.add(tabId);
  }
  selected = tabId;
  await chrome.debugger.sendCommand({ tabId }, "Page.enable");
  return { id: `tab-${tabId}`, url: tab.url };
}

export async function dispatch(action, params) {
  switch (action) {
    case "status": {
      const tab = selected === undefined ? null : await chrome.tabs.get(selected);
      return { title: tab?.title?.slice(0, 200) ?? null,
        selected: selected !== undefined,
        browser: navigator.userAgent.includes("Edg/") ? "Edge" : "Chrome" };
    }
    case "focus": {
      if (selected === undefined) throw new Error("Select a tab first.");
      const tab = await chrome.tabs.update(selected, { active: true });
      await chrome.windows.update(tab.windowId, { focused: true });
      return {};
    }
    case "tabs": {
      const tabs = await chrome.tabs.query({});
      return tabs
        .filter((tab) => {
          try {
            webUrl(tab.url);
            return !tab.incognito;
          } catch {
            return false;
          }
        })
        .map((tab) => ({
          id: `tab-${tab.id}`,
          title: tab.title?.slice(0, 200),
          url: tab.url,
          selected: tab.id === selected,
        }));
    }
    case "select":
      if (!/^tab-\d+$/.test(params.id))
        throw new Error("List tabs and select a valid tab.");
      return select(Number(params.id.slice(4)));
    case "open": {
      const url = webUrl(params.url);
      if (selected === undefined) {
        const tab = await chrome.tabs.create({ url, active: false });
        await waitReady(tab.id);
        return select(tab.id);
      }
      await chrome.tabs.update(selected, { url });
      await waitReady(selected);
      return { id: `tab-${selected}`, url };
    }
    case "cdp": {
      if (selected === undefined || !attached.has(selected))
        throw new Error("Select a tab or open a page first.");
      webUrl((await chrome.tabs.get(selected)).url);
      if (!allowedMethods.has(params.method))
        throw new Error("Unsupported browser command.");
      const result = await chrome.debugger.sendCommand(
        { tabId: selected },
        params.method,
        params.params || {},
      );
      if (
        ["Page.reload", "Page.navigateToHistoryEntry"].includes(params.method)
      )
        await waitReady(selected);
      return result;
    }
    case "detach":
      await detach();
      return {};
    default:
      throw new Error("Unsupported browser command.");
  }
}

async function waitReady(tabId) {
  const deadline = Date.now() + 15000;
  while ((await chrome.tabs.get(tabId)).status === "loading") {
    if (Date.now() > deadline) throw new Error("Page is still loading.");
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

async function connect(usePairingAddress = false) {
  if (
    connecting ||
    (socket &&
      [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState))
  )
    return;
  connecting = true;
  try {
    const { pairing } = await chrome.storage.local.get("pairing");
    if (!pairing) return;
    let endpoint = pairing.url;
    if (!usePairingAddress) {
      try {
        const discovery = await chrome.runtime.sendNativeMessage(
          "com.suzent.browser", { action: "endpoint" },
        );
        if (discovery?.url) endpoint = discovery.url;
      } catch {
        // Host registration may be blocked by browser policy; retain the paired address.
      }
    }
    const url = new URL(endpoint);
    if (
      url.protocol !== "ws:" ||
      url.hostname !== "127.0.0.1" ||
      url.pathname !== "/ws/browser-extension"
    )
      return;
    const ws = new WebSocket(url);
    socket = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ token: pairing.token }));
      heartbeat = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN)
          ws.send(JSON.stringify({ type: "ping" }));
      }, 20000);
    };
    ws.onmessage = ({ data }) => {
      const message = JSON.parse(data);
      if (message.type === "ready") {
        chrome.action.setBadgeText({ text: "ON" });
        return;
      }
      if (!Number.isInteger(message.id)) return;
      queue = queue
        .catch(() => {})
        .then(async () => {
          if (socket !== ws || ws.readyState !== WebSocket.OPEN) return;
          try {
            const result = await dispatch(message.action, message.params || {});
            if (socket === ws)
              emit({ type: "result", id: message.id, result: result ?? {} });
          } catch {
            emit({
              type: "result",
              id: message.id,
              error:
                "Browser action failed. Select a web tab and retry; check whether DevTools or browser policy prevents extension control.",
            });
          }
        });
    };
    ws.onclose = ({ code }) => {
      if (socket !== ws) return;
      socket = undefined;
      if (code === 1008) void chrome.storage.local.remove("pairing");
      clearInterval(heartbeat);
      chrome.action.setBadgeText({ text: "" });
      queue = queue.catch(() => {}).then(detach);
    };
  } finally {
    connecting = false;
  }
}

function flushFrame() {
  frameTimer = undefined;
  if (selected === undefined || socket?.readyState !== WebSocket.OPEN) {
    pendingFrame = undefined;
    return;
  }
  if (socket.bufferedAmount >= 512 * 1024) {
    frameTimer = setTimeout(flushFrame, 100);
    return;
  }
  if (pendingFrame) {
    emit({ type: "event", method: "Page.screencastFrame", params: pendingFrame });
    pendingFrame = undefined;
  }
}

chrome.debugger.onEvent.addListener((source, method, params) => {
  if (source.tabId === selected && method === "Page.screencastFrame") {
    // Acknowledge locally so slow previews cannot block agent commands.
    void chrome.debugger.sendCommand(source, "Page.screencastFrameAck", {
      sessionId: params.sessionId,
    }).catch(() => {});
    pendingFrame = params;
    if (!frameTimer) frameTimer = setTimeout(flushFrame, 100);
    return;
  }
  if (
    source.tabId === selected &&
    ["Page.screencastFrame", "Page.frameNavigated"].includes(method)
  ) {
    emit({ type: "event", method, params });
  }
});
chrome.debugger.onDetach.addListener(({ tabId }, reason) => {
  if (!attached.delete(tabId)) return;
  selected = undefined;
  emit({ type: "event", method: "detached", params: {} });
  if (reason === "canceled_by_user") {
    void chrome.storage.local.remove("pairing");
    socket?.close();
  }
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  (async () => {
    if (message.type === "pair") {
      const url = new URL(sender.url);
      if (
        url.origin !== message.origin ||
        url.hostname !== "127.0.0.1" ||
        url.protocol !== "http:" ||
        url.pathname !== "/browser/extension/connect" ||
        !/^[A-Za-z0-9_-]{43}$/.test(message.token)
      )
        throw new Error("Invalid pairing request");
      if (socket) {
        socket.onclose = null;
        socket.close();
        socket = undefined;
      }
      clearInterval(heartbeat);
      await queue.catch(() => {});
      await detach();
      url.protocol = "ws:";
      url.pathname = "/ws/browser-extension";
      url.hash = "";
      await chrome.storage.local.set({
        pairing: { url: url.href, token: message.token },
      });
      await connect(true);
      return { ok: true };
    }
    if (sender.url !== chrome.runtime.getURL("popup.html"))
      return { ok: false };
    if (message.type === "disconnect") {
      await chrome.storage.local.remove("pairing");
      socket?.close();
      await detach();
    } else if (message.type === "connect") await connect();
    return { connected: socket?.readyState === WebSocket.OPEN };
  })().then(respond, () => respond({ ok: false }));
  return true;
});
chrome.alarms.create("reconnect", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => void connect());
chrome.runtime.onStartup.addListener(() => void connect());
void connect();
