import Foundation
import Testing
@testable import SuzentCore

@Test func connectionCompletesBeforeDeadline() async throws {
    let value = try await withConnectionTimeout(.seconds(1)) { 42 }
    #expect(value == 42)
}

@Test func stalledConnectionTimesOut() async {
    do {
        try await withConnectionTimeout(.milliseconds(20)) {
            try await Task.sleep(for: .seconds(60))
        }
        Issue.record("A stalled connection must time out")
    } catch {
        #expect((error as? URLError)?.code == .timedOut)
    }
}

@Test func cancelledConnectionDoesNotWaitForDeadline() async {
    let attempt = Task {
        try await withConnectionTimeout(.seconds(60)) {
            try await Task.sleep(for: .seconds(60))
        }
    }
    attempt.cancel()
    do {
        try await attempt.value
        Issue.record("A cancelled connection must not succeed")
    } catch {
        #expect(error is CancellationError)
    }
}

@Test func reconnectRacesSlowAddressesAndCancelsLosers() async throws {
    let route = try await withConnectionTimeout(.seconds(2)) {
        try await resolveConnectionRoute(origins: ["slow", "fast"], hasRelay: true) { route in
            if route != .direct("fast") { try await Task.sleep(for: .seconds(60)) }
        }
    }
    #expect(route == .direct("fast"))
}

@Test func reconnectRelayDoesNotWaitForDirectTimeout() async throws {
    let route = try await withConnectionTimeout(.seconds(2)) {
        try await resolveConnectionRoute(origins: ["slow"], hasRelay: true) { route in
            if route != .relay { try await Task.sleep(for: .seconds(60)) }
        }
    }
    #expect(route == .relay)
}

@Test func reconnectReportsAllRoutesFailing() async {
    do {
        _ = try await resolveConnectionRoute(origins: ["one", "two"], hasRelay: true) { _ in
            throw URLError(.cannotConnectToHost)
        }
        Issue.record("Unreachable routes must fail")
    } catch { #expect(error is PairingError) }
}

@Test func reconnectCancellationDoesNotBecomeUnreachable() async {
    let attempt = Task {
        try await resolveConnectionRoute(origins: ["slow"], hasRelay: true) { _ in
            try await Task.sleep(for: .seconds(60))
        }
    }
    attempt.cancel()
    do {
        _ = try await attempt.value
        Issue.record("Cancelled reconnect must not succeed")
    } catch { #expect(error is CancellationError) }
}
