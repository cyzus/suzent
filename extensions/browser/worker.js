let socket;
let connecting = false;
let pairingRevision = 0;
let selected;
let heartbeat;
let frameTimer;
let pendingFrame;
let queue = Promise.resolve();
let generation = 0;
let cleanup = Promise.resolve();
const attached = new Map();
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
  const ids = [...attached.keys()];
  attached.clear();
  await Promise.allSettled(
    ids.map((tabId) => chrome.debugger.detach({ tabId })),
  );
}

function requireCurrent(epoch) {
  if (epoch !== generation) throw new Error("Browser connection changed.");
}

function resetActions() {
  generation++;
  queue = Promise.resolve();
  // Detach must bypass a renderer command that may never settle.
  cleanup = Promise.allSettled([cleanup, detach()]).then(() => undefined);
  return cleanup;
}

async function select(tabId, epoch) {
  const tab = await chrome.tabs.get(tabId);
  requireCurrent(epoch);
  if (tab.incognito) throw new Error("Private tabs are not supported.");
  webUrl(tab.url);
  if (selected !== tabId) await detach();
  requireCurrent(epoch);
  if (!attached.has(tabId)) {
    attached.set(tabId, epoch);
    try {
      await chrome.debugger.attach({ tabId }, "1.3");
    } catch (error) {
      if (attached.get(tabId) === epoch) attached.delete(tabId);
      throw error;
    }
    if (epoch !== generation) {
      if (!attached.has(tabId))
        await chrome.debugger.detach({ tabId }).catch(() => {});
      requireCurrent(epoch);
    }
  }
  selected = tabId;
  await chrome.debugger.sendCommand({ tabId }, "Page.enable");
  return { id: `tab-${tabId}`, url: tab.url };
}

export async function dispatch(action, params, epoch = generation) {
  requireCurrent(epoch);
  switch (action) {
    case "status": {
      const tab =
        selected === undefined ? null : await chrome.tabs.get(selected);
      return {
        title: tab?.title?.slice(0, 200) ?? null,
        selected: selected !== undefined,
        browser: navigator.userAgent.includes("Edg/") ? "Edge" : "Chrome",
      };
    }
    case "focus": {
      if (selected === undefined) throw new Error("Select a tab first.");
      const tab = await chrome.tabs.update(selected, { active: true });
      requireCurrent(epoch);
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
      return select(Number(params.id.slice(4)), epoch);
    case "open": {
      const url = webUrl(params.url);
      if (selected === undefined) {
        const tab = await chrome.tabs.create({ url, active: false });
        await waitReady(tab.id, epoch);
        return select(tab.id, epoch);
      }
      const tabId = selected;
      await chrome.tabs.update(tabId, { url });
      await waitReady(tabId, epoch);
      return { id: `tab-${tabId}`, url };
    }
    case "cdp": {
      if (selected === undefined || !attached.has(selected))
        throw new Error("Select a tab or open a page first.");
      const tabId = selected;
      webUrl((await chrome.tabs.get(tabId)).url);
      requireCurrent(epoch);
      if (!allowedMethods.has(params.method))
        throw new Error("Unsupported browser command.");
      const result = await chrome.debugger.sendCommand(
        { tabId },
        params.method,
        params.params || {},
      );
      if (
        ["Page.reload", "Page.navigateToHistoryEntry"].includes(params.method)
      )
        await waitReady(tabId, epoch);
      return result;
    }
    case "detach":
      await detach();
      return {};
    default:
      throw new Error("Unsupported browser command.");
  }
}

async function waitReady(tabId, epoch) {
  requireCurrent(epoch);
  const deadline = Date.now() + 15000;
  while ((await chrome.tabs.get(tabId)).status === "loading") {
    requireCurrent(epoch);
    if (Date.now() > deadline) throw new Error("Page is still loading.");
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  requireCurrent(epoch);
}

function authenticate(pairing) {
  const url = new URL(pairing.url);
  if (
    url.protocol !== "ws:" ||
    url.hostname !== "127.0.0.1" ||
    url.pathname !== "/ws/browser-extension"
  )
    throw new Error("Invalid browser endpoint.");
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const messages = [];
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error("Browser pairing timed out."));
    }, 10000);
    ws.onopen = () => ws.send(JSON.stringify({ token: pairing.token }));
    ws.onmessage = ({ data }) => {
      if (JSON.parse(data).type === "ready") {
        clearTimeout(timer);
        resolve({ ws, messages });
      } else if (messages.length < 64) messages.push(data);
      else ws.close();
    };
    ws.onclose = () => {
      clearTimeout(timer);
      reject(new Error("Browser pairing was rejected."));
    };
    ws.onerror = () => ws.close();
  });
}

async function adopt({ ws, messages }, revision) {
  if (revision !== pairingRevision) {
    ws.close();
    throw new Error("Pairing changed.");
  }
  await resetActions();
  if (revision !== pairingRevision) {
    ws.close();
    throw new Error("Pairing changed.");
  }
  if (ws.readyState !== WebSocket.OPEN)
    throw new Error("Browser disconnected.");
  const previous = socket;
  if (previous && previous !== ws) {
    previous.onclose = null;
    previous.close();
  }
  clearInterval(heartbeat);
  const epoch = generation;
  socket = ws;
  chrome.action.setBadgeText({ text: "ON" });
  heartbeat = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ type: "ping" }));
  }, 20000);
  ws.onmessage = ({ data }) => {
    if (socket !== ws) return;
    const message = JSON.parse(data);
    if (!Number.isInteger(message.id)) return;
    queue = queue
      .catch(() => {})
      .then(async () => {
        if (socket !== ws || ws.readyState !== WebSocket.OPEN) return;
        try {
          const result = await dispatch(
            message.action,
            message.params || {},
            epoch,
          );
          if (socket === ws)
            emit({ type: "result", id: message.id, result: result ?? {} });
        } catch {
          if (socket !== ws) return;
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
    if (code === 1008) {
      pairingRevision++;
      void chrome.storage.local.remove("pairing");
    }
    clearInterval(heartbeat);
    chrome.action.setBadgeText({ text: "" });
    void resetActions();
  };
  for (const data of messages) ws.onmessage({ data });
}

async function connect() {
  if (
    connecting ||
    (socket &&
      [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState))
  )
    return;
  connecting = true;
  const revision = pairingRevision;
  try {
    const { pairing } = await chrome.storage.local.get("pairing");
    if (!pairing) return;
    let endpoint = pairing.url;
    try {
      const discovery = await chrome.runtime.sendNativeMessage(
        "com.suzent.browser",
        { action: "endpoint" },
      );
      if (discovery?.url) endpoint = discovery.url;
    } catch {
      // Host registration may be blocked by browser policy; retain the paired address.
    }
    await cleanup;
    await adopt(await authenticate({ ...pairing, url: endpoint }), revision);
  } catch {
    // Keep saved credentials until a replacement is authenticated or explicitly revoked.
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
    emit({
      type: "event",
      method: "Page.screencastFrame",
      params: pendingFrame,
    });
    pendingFrame = undefined;
  }
}

chrome.debugger.onEvent.addListener((source, method, params) => {
  if (source.tabId === selected && method === "Page.screencastFrame") {
    // Acknowledge locally so slow previews cannot block agent commands.
    void chrome.debugger
      .sendCommand(source, "Page.screencastFrameAck", {
        sessionId: params.sessionId,
      })
      .catch(() => {});
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
      url.protocol = "ws:";
      url.pathname = "/ws/browser-extension";
      url.hash = "";
      const pairing = { url: url.href, token: message.token };
      const expectedRevision = pairingRevision;
      const candidate = await authenticate(pairing);
      if (expectedRevision !== pairingRevision) {
        candidate.ws.close();
        throw new Error("Pairing changed.");
      }
      const revision = ++pairingRevision;
      await chrome.storage.local.set({ pairing });
      await adopt(candidate, revision);
      return { ok: true };
    }
    if (sender.url !== chrome.runtime.getURL("popup.html"))
      return { ok: false };
    if (message.type === "disconnect") {
      pairingRevision++;
      await chrome.storage.local.remove("pairing");
      socket?.close();
      await resetActions();
    } else if (message.type === "connect") await connect();
    return { connected: socket?.readyState === WebSocket.OPEN };
  })().then(respond, () => respond({ ok: false }));
  return true;
});
chrome.alarms.create("reconnect", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => void connect());
chrome.runtime.onStartup.addListener(() => void connect());
void connect();
