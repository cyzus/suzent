/** One preview connection, including retries, owned by one visible view. */
export function connectBrowserPreview(
  url: string,
  onSocket: (socket: WebSocket | null) => void,
  onStatus: (status: 'connected' | 'disconnected' | 'connecting') => void,
  onMessage: (event: MessageEvent) => void
): () => void {
  let disposed = false;
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout>;
  const connect = (): void => {
    if (disposed) return;
    onStatus('connecting');
    const ws = new WebSocket(url);
    socket = ws;
    onSocket(ws);
    ws.onopen = () => {
      if (!disposed) onStatus('connected');
    };
    ws.onmessage = (event) => {
      if (!disposed) onMessage(event);
    };
    ws.onclose = () => {
      if (disposed) return;
      socket = null;
      onSocket(null);
      onStatus('disconnected');
      retry = setTimeout(connect, 3000);
    };
  };
  connect();
  return () => {
    disposed = true;
    clearTimeout(retry);
    onSocket(null);
    if (socket) {
      socket.onclose = null;
      socket.onopen = null;
      socket.onmessage = null;
      socket.close();
      socket = null;
    }
  };
}
