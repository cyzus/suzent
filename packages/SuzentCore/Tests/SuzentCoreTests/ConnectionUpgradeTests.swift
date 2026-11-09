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
                  validate: { _ in }, install: { state.installed.append($0) }, discard: { candidate in
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
                  validate: { _ in }, install: { state.installed.append($0) }, discard: { candidate in
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
                  validate: { _ in }, install: { state.installed.append($0) }, discard: { candidate in
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
                  validate: { _ in }, install: { state.installed.append($0) }, discard: { candidate in
        state.discarded.append(candidate)
    })
    try await Task.sleep(for: .milliseconds(50))
    #expect(state.installed.isEmpty)
    #expect(state.discarded.isEmpty)
}

@MainActor @Test func lostDirectRouteAfterIdleWaitKeepsRelay() async throws {
    let state = UpgradeState()
    let upgrade = ConnectionUpgrade<Int>()
    var validated = false
    upgrade.start(prepare: { 1 }, isCurrent: { true }, isIdle: { state.idle },
                  validate: { _ in validated = true; throw URLError(.cannotConnectToHost) },
                  install: { state.installed.append($0) }, discard: { state.discarded.append($0) })
    try await Task.sleep(for: .milliseconds(50))
    #expect(!validated)
    state.idle = true
    try await Task.sleep(for: .milliseconds(300))
    #expect(validated)
    #expect(state.installed.isEmpty)
    #expect(state.discarded == [1])
    upgrade.cancel()
}

@MainActor @Test func sessionChangeDuringValidationDiscardsDirectRoute() async throws {
    let state = UpgradeState()
    let upgrade = ConnectionUpgrade<Int>()
    upgrade.start(prepare: { 1 }, isCurrent: { state.current }, isIdle: { true },
                  validate: { _ in
        await Task.yield()
        state.current = false
    }, install: { state.installed.append($0) }, discard: { state.discarded.append($0) })
    try await Task.sleep(for: .milliseconds(100))
    #expect(state.installed.isEmpty)
    #expect(state.discarded == [1])
    upgrade.cancel()
}

@MainActor @Test func workStartingDuringValidationDefersInstallation() async throws {
    let state = UpgradeState()
    state.idle = true
    var validations = 0
    let upgrade = ConnectionUpgrade<Int>()
    upgrade.start(prepare: { 1 }, isCurrent: { true }, isIdle: { state.idle },
                  validate: { _ in
        validations += 1
        if validations == 1 { state.idle = false }
    }, install: { state.installed.append($0) }, discard: { state.discarded.append($0) })
    try await Task.sleep(for: .milliseconds(50))
    #expect(state.installed.isEmpty)
    state.idle = true
    try await Task.sleep(for: .milliseconds(300))
    #expect(validations == 2)
    #expect(state.installed == [1])
    #expect(state.discarded.isEmpty)
    upgrade.cancel()
}
