import Foundation
import Testing
@testable import SuzentCore

@Test func sharedActivityTimingContract() throws {
    struct Fixture: Decodable { let name: String; let messages: [ChatMessage]; let seconds: Int? }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/activity-timing-fixtures.json"))
    for fixture in try JSONDecoder().decode([Fixture].self, from: data) {
        #expect(presentMessages(fixture.messages).last?.workedSeconds == fixture.seconds, "\(fixture.name)")
    }
}

@Test func activityDisclosurePreservesAnswerAndRecognizesFailedEnvelope() {
    let parts = [MessagePart(type: "text", text: "Checking"), MessagePart(type: "tool", toolName: "read_file", output: #"{"success":false,"error":"File missing"}"#, state: "completed"), MessagePart(type: "text", text: "Final answer")]
    #expect(activityFinalStart(parts) == 2)
    #expect(activityFailed(parts[1]))
    #expect(activityDetail(parts[1].output, output: true) == "File missing")
    #expect(activityDuration(65) == "1m 5s")
    #expect(activityDuration(0) == "0s")
    #expect(activityDetail(#"{"message":"Saved","success":true}"#, output: true) == "Saved")
    #expect(activityFinalStart([.init(type: "text", text: "Answer")]) == 0)
}

@Test func toolIconsAndMotionFollowDesktop() {
    #expect(activityToolIcon("Read") == "document-text")
    #expect(activityToolIcon("mcp__server__memory_search") == "cpu-chip")
    #expect(activityToolIcon("query_database") == "circle-stack")
    #expect(activityToolIcon("mystery") == "wrench-screwdriver")
    #expect(activityToolIcon("run_command", approval: "pending") == "clock")
    #expect(activityToolIcon("run_command", approval: "denied") == "no-symbol")
    #expect(activityToolAnimation("Bash", running: true) == "terminal")
    #expect(activityToolAnimation("grep_search", running: true) == "radar")
    #expect(activityToolAnimation("browser_action", running: true) == "cursor")
    #expect(activityToolAnimation("grep_search", running: true, hasOutput: true) == "none")
    #expect(activityToolAnimation("grep_search", approval: "pending") == "pending")
    #expect(abs(Curve.linear.at(0.5) - 0.5) < 1e-6)
    #expect(abs(Curve.easeInOut.at(0.5) - 0.5) < 1e-3)
    #expect(activityRunningSurface("grep_search") == "scan")
    #expect(activityRunningSurface("Read") == "dots")
    #expect(activityRunningSurface("Bash") == "mono")
    #expect(activityRunningSurface("vision_describe") == "scan")
    #expect(activityRunningSurface("mystery") == "mono")
    #expect(abs(runningSurfaceFrame("mono", seconds: 1.35 * 0.25).wave - 0.25) < 1e-9)
    #expect(abs(runningSurfaceFrame("dots", seconds: 0.7).gridShift - 6) < 1e-9)
    #expect(thinkingLabelFrame(seconds: 1.8 * 0.13) == ThinkingLabelFrame(sweep: 0.2, barStart: 0, barEnd: 0.5))
    #expect(thinkingLabelFrame(seconds: 1.8 * 0.3) == ThinkingLabelFrame(sweep: 0.2, barStart: 0, barEnd: 1))
    #expect(thinkingLabelFrame(seconds: 1.8 * 0.9).barStart == 1)
    #expect(abs(thinkingLabelFrame(seconds: 1.8 * 0.9).sweep - 0.35) < 1e-9)
    #expect(abs(toolIconPose("pending", seconds: 1.4 * 0.3).rotation - 12) < 1e-6)
    #expect(toolIconPose("scan", seconds: 0).sweepY == -7)
    #expect(abs(toolIconPose("terminal", seconds: 0.5).alpha - 0.35) < 1e-6)
    #expect(abs(cycle(2.25, 1) - 0.25) < 1e-9)
    #expect(abs(cycle(1.25, 1, alternate: true) - 0.75) < 1e-9)
}

@Test @MainActor func collapsedStreamingRailStaysClosedAcrossRemountAndTokenUpdates() {
    let choices = RailChoices()
    let chunk = [MessagePart(type: "reasoning", text: "Looking")]
    let key = "\(railScope(chatId: "chat", messageKey: "live1")):\(railChunkKey(chunk, index: 0))"
    #expect(railExpanded(choice: choices.choice(key), live: true, current: true, waiting: false))
    choices.set(key, expanded: false)
    // A recycled row has no local choice and reads the same conversation store.
    #expect(railExpanded(choice: choices.choice(key), live: true, current: true, waiting: false) == false)
    let updated = chunk + [MessagePart(type: "tool", toolName: "read_file", toolCallId: "t1", state: "running")]
    #expect(railChunkKey(updated, index: 0) == railChunkKey(chunk, index: 0))
    let same = "\(railScope(chatId: "chat", messageKey: "live1")):\(railChunkKey(updated, index: 0))"
    #expect(railExpanded(choice: choices.choice(same), live: true, current: true, waiting: false) == false)
}

@Test @MainActor func reopeningAndANewStreamAreSeparateFromTheCollapsedRail() {
    let choices = RailChoices()
    let key = "\(railScope(chatId: "chat", messageKey: "live1")):i0"
    choices.set(key, expanded: false)
    choices.set(key, expanded: true)
    #expect(railExpanded(choice: choices.choice(key), live: true, current: true, waiting: false))
    let first = nextStreamGeneration(0, wasStreaming: false, streaming: true)
    let held = nextStreamGeneration(first.generation, wasStreaming: first.streaming, streaming: true)
    let stopped = nextStreamGeneration(held.generation, wasStreaming: held.streaming, streaming: false)
    let second = nextStreamGeneration(stopped.generation, wasStreaming: stopped.streaming, streaming: true)
    #expect(held.generation == 1)
    #expect(second.generation == 2)
    let nextKey = "\(railScope(chatId: "chat", messageKey: "live\(second.generation)")):i0"
    #expect(choices.choice(nextKey) == nil)
    #expect(railExpanded(choice: choices.choice(nextKey), live: true, current: true, waiting: false))
}

@Test @MainActor func aNewChatDoesNotReuseRailChoices() {
    let previous = RailChoices()
    previous.set("\(railScope(chatId: "a", messageKey: "m0")):i0", expanded: false)
    let next = RailChoices()
    #expect(next.choice("\(railScope(chatId: "b", messageKey: "m0")):i0") == nil)
    #expect(railExpanded(choice: next.choice("\(railScope(chatId: "b", messageKey: "m0")):i0"), live: true, current: true, waiting: false))
}

@Test func approvalKeepsTheRailOpenAndAFinishedUntouchedRailCloses() {
    #expect(railExpanded(choice: false, live: true, current: true, waiting: true))
    #expect(railExpanded(choice: nil, live: false, current: false, waiting: false) == false)
}

@Test func streamingStaysInkWhenAnEarlierToolFailed() {
    let parts = [
        MessagePart(type: "tool", toolName: "read_file", toolCallId: "a", state: "error"),
        MessagePart(type: "tool", toolName: "grep_search", toolCallId: "b", state: "running"),
    ]
    #expect(activityHeaderTone(parts, live: true, current: true) == .streaming)
    #expect(activityToneToken(.streaming) == "text")
    #expect(activityToneToken(.streaming) != "blue")
    #expect(activityItemTone(failed: true, pending: false, active: false) == .failed)
    #expect(activityItemTone(failed: false, pending: false, active: true) == .streaming)
    #expect(activityToneToken(.failed) == "danger")
    #expect(activitySummary(parts, live: true).contains { $0.kind == "failed" && $0.count == 1 })
}

@Test func aMixOfSuccessAndFailureDoesNotPaintTheWholeHeaderAsFailed() {
    let parts = [
        MessagePart(type: "tool", toolName: "read_file", toolCallId: "a", state: "completed"),
        MessagePart(type: "tool", toolName: "write_file", toolCallId: "b", state: "error"),
    ]
    #expect(activityHeaderTone(parts, live: false, current: false) == .idle)
    #expect(activityToneToken(.idle) == "muted")
    #expect(activityItemTone(failed: true, pending: false, active: false) == .failed)
    #expect(activityItemTone(failed: false, pending: false, active: false) == .idle)
    #expect(activitySummary(parts, live: false).contains { $0.kind == "failed" && $0.count == 1 })
}

@Test func everyToolFailingIsStillAFailedHeaderOnceTheStreamEnds() {
    let parts = [
        MessagePart(type: "tool", toolName: "read_file", toolCallId: "a", state: "error"),
        MessagePart(type: "tool", toolName: "grep_search", toolCallId: "b", state: "denied"),
    ]
    #expect(activityHeaderTone(parts, live: false, current: false) == .failed)
    #expect(activityToneToken(.failed) == "danger")
}
