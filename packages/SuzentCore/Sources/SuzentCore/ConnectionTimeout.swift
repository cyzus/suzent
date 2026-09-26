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
