public enum ComposerAction: Equatable, Sendable {
    case voice, send, loading, connecting, hangUp, stop

    public static func resolve(hasContent: Bool, busy: Bool, running: Bool, voiceActive: Bool, voiceConnecting: Bool) -> Self {
        if voiceActive { return voiceConnecting ? .connecting : .hangUp }
        if running { return .stop }
        if busy { return .loading }
        if hasContent { return .send }
        return .voice
    }
}
