#if canImport(JavaScriptCore)
import Foundation
import Testing
@testable import SuzentCore

@Test func suzentBotResolvesTheDesktopStages() {
    let session = SuzentBotSession(seed: 1)
    #expect(session.resolveStage(hasPending: true, isError: true, isThinking: false, tool: "run_command", isActive: true) == "approval")
    #expect(session.resolveStage(hasPending: false, isError: true, isThinking: false, tool: "write_file", isActive: true) == "error")
    #expect(session.resolveStage(hasPending: false, isError: false, isThinking: true, tool: nil, isActive: true) == "thinking")
    #expect(session.resolveStage(hasPending: false, isError: false, isThinking: false, tool: "read_file", isActive: true) == "reading")
    #expect(session.resolveStage(hasPending: false, isError: false, isThinking: false, tool: "WebSearch", isActive: true) == "searching")
    #expect(session.resolveStage(hasPending: false, isError: false, isThinking: false, tool: nil, isActive: false) == "idle")
}

@Test func suzentBotPathAndReducedFrame() {
    let path = parseBotPath("M0 0L10 0L10 10Z")
    #expect(path.count == 4)
    let moved = parseBotTransform("translate(4 5) scale(2)")
    #expect(abs(moved.x(2, 0) - 8) < 1e-9)
    let session = SuzentBotSession(seed: 1)
    let frame = session.frame(json: #"{"stage":"idle","time":0,"reducedMotion":true,"size":32,"holdWhenIdle":true}"#)
    #expect(frame.settled)
    #expect(frame.nodes.contains { $0.tag == "defs" })
}
#endif
