import Foundation

public func withConnectionTimeout<Value: Sendable>(
    _ duration: Duration = .seconds(20),
    operation: @escaping @Sendable () async throws -> Value
) async throws -> Value {
    try await withThrowingTaskGroup(of: Value.self) { group in
        group.addTask { try await operation() }
        group.addTask {
            try await Task.sleep(for: duration)
            throw URLError(.timedOut)
        }
        defer { group.cancelAll() }
        return try await group.next()!
    }
}

public enum ConnectionRoute: Sendable, Equatable {
    case direct(String)
    case relay
}

public func resolveConnectionRoute(
    origins: [String], hasRelay: Bool,
    probe: @escaping @Sendable (ConnectionRoute) async throws -> Void
) async throws -> ConnectionRoute {
    try await withThrowingTaskGroup(of: ConnectionRoute?.self) { group in
        var visited = Set<String>()
        let routes = origins.filter { visited.insert($0).inserted }.map(ConnectionRoute.direct)
            + (hasRelay ? [.relay] : [])
        for route in routes {
            group.addTask {
                do {
                    if route == .relay && !origins.isEmpty { try await Task.sleep(for: .milliseconds(300)) }
                    try Task.checkCancellation()
                    try await probe(route)
                    return route
                } catch { try Task.checkCancellation(); return nil }
            }
        }
        defer { group.cancelAll() }
        for try await route in group {
            if let route { try Task.checkCancellation(); return route }
        }
        throw PairingError.unreachable
    }
}
