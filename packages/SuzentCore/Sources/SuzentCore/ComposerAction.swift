public enum ComposerAction: Equatable, Sendable {
    case voice, send, loading, connecting, hangUp, stop, queue, redirect

    /// While a turn runs, typed content is redirected or queued like Enter and Cmd/Ctrl+Enter on desktop;
    /// `canRedirect` is false for attachments alone or a desktop without redirects, which leaves queueing.
    public static func resolve(hasContent: Bool, busy: Bool, running: Bool, voiceActive: Bool, voiceConnecting: Bool,
                               canRedirect: Bool = false) -> Self {
        if voiceActive { return voiceConnecting ? .connecting : .hangUp }
        if running && hasContent { return busy ? .loading : canRedirect ? .redirect : .queue }
        if running { return .stop }
        if busy { return .loading }
        if hasContent { return .send }
        return .voice
    }
}
