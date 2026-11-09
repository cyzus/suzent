import Foundation

/// Owns a speculative client until the current session can adopt it without interrupting work.
@MainActor public final class ConnectionUpgrade<Candidate: Sendable> {
    private var task: Task<Void, Never>?

    public init() {}

    public func cancel() {
        task?.cancel()
        task = nil
    }

    public func start(
        prepare: @escaping @Sendable () async throws -> Candidate,
        isCurrent: @escaping @MainActor () -> Bool,
        isIdle: @escaping @MainActor () -> Bool,
        validate: @escaping @MainActor (Candidate) async throws -> Void,
        install: @escaping @MainActor (Candidate) throws -> Void,
        discard: @escaping @MainActor (Candidate) -> Void
    ) {
        cancel()
        task = Task {
            do {
                let candidate = try await prepare()
                var installed = false
                defer { if !installed { discard(candidate) } }
                while !Task.isCancelled && isCurrent() {
                    if isIdle() {
                        try await validate(candidate)
                        try Task.checkCancellation()
                        guard isCurrent() else { return }
                        if isIdle() {
                            try install(candidate)
                            installed = true
                            return
                        }
                    }
                    try await Task.sleep(for: .milliseconds(200))
                }
            } catch {
                // An optional route upgrade must never replace a working session's error state.
            }
        }
    }
}
