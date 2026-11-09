import Foundation
import Testing
@testable import SuzentCore

@MainActor private final class UpgradeState {
    var current = true
    var idle = false
    var installed: [Int] = []
    var discarded: [Int] = []
}

@MainActor @Test func upgradeWaitsForIdleWithoutResettingSession() async throws {
    let state = UpgradeState()
    let upgrade = ConnectionUpgrade<Int>()
    upgrade.start(prepare: { 1 }, isCurrent: { state.current }, isIdle: { state.idle },
                  install: { state.installed.append($0) }, discard: { candidate in
        state.discarded.append(candidate)
    })
    try await Task.sleep(for: .milliseconds(50))
    #expect(state.installed.isEmpty)
    state.idle = true
    try await Task.sleep(for: .milliseconds(300))
    #expect(state.installed == [1])
    #expect(state.discarded.isEmpty)
    upgrade.cancel()
}

@MainActor @Test func staleUpgradeDiscardsCandidate() async throws {
    let state = UpgradeState()
    let upgrade = ConnectionUpgrade<Int>()
    upgrade.start(prepare: { 1 }, isCurrent: { state.current }, isIdle: { state.idle },
                  install: { state.installed.append($0) }, discard: { candidate in
        state.discarded.append(candidate)
    })
    try await Task.sleep(for: .milliseconds(50))
    state.current = false
    state.idle = true
    try await Task.sleep(for: .milliseconds(300))
    #expect(state.installed.isEmpty)
    #expect(state.discarded == [1])
    upgrade.cancel()
}

@MainActor @Test func cancelledUpgradeClosesPreparedClient() async throws {
    let state = UpgradeState()
    let upgrade = ConnectionUpgrade<Int>()
    upgrade.start(prepare: { 1 }, isCurrent: { true }, isIdle: { false },
                  install: { state.installed.append($0) }, discard: { candidate in
        state.discarded.append(candidate)
    })
    try await Task.sleep(for: .milliseconds(50))
    upgrade.cancel()
    try await Task.sleep(for: .milliseconds(50))
    #expect(state.installed.isEmpty)
    #expect(state.discarded == [1])
}

@MainActor @Test func failedUpgradeDoesNotInstall() async throws {
    let state = UpgradeState()
    let upgrade = ConnectionUpgrade<Int>()
    upgrade.start(prepare: { throw URLError(.cannotConnectToHost) }, isCurrent: { true }, isIdle: { true },
                  install: { state.installed.append($0) }, discard: { candidate in
        state.discarded.append(candidate)
    })
    try await Task.sleep(for: .milliseconds(50))
    #expect(state.installed.isEmpty)
    #expect(state.discarded.isEmpty)
}
