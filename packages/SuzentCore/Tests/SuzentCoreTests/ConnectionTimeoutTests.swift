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
