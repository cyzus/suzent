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
    #expect(abs(toolIconPose("pending", seconds: 1.4 * 0.3).rotation - 12) < 1e-6)
    #expect(toolIconPose("scan", seconds: 0).sweepY == -7)
    #expect(abs(toolIconPose("terminal", seconds: 0.5).alpha - 0.35) < 1e-6)
    #expect(abs(cycle(2.25, 1) - 0.25) < 1e-9)
    #expect(abs(cycle(1.25, 1, alternate: true) - 0.75) < 1e-9)
}
