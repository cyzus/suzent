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

@Test func suzentBotParsesStyleOpacityStrings() {
    let frame = SuzentBotFrame.parse(##"{"viewBox":"0 0 1 1","fg":"#000","bg":"#fff","settled":true,"nodes":[{"tag":"g","attrs":{},"opacity":"0.420","children":[]}]}"##)
    #expect(abs(frame.nodes[0].opacity - 0.42) < 0.0001)
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

@Test func toolGlyphsMatchDesktopFrames() throws {
    let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("mobile-contract/tool-glyph-frames.json")
    let scenarios = try JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as! [[String: Any]]
    let session = SuzentBotSession()
    for scenario in scenarios {
        let tool = scenario["tool"] as! String, animation = scenario["animation"] as! String
        for frame in scenario["frames"] as! [[String: Any]] {
            let expected = SuzentBotFrame.parse(String(data: try JSONSerialization.data(withJSONObject: frame["scene"]!), encoding: .utf8)!)
            let actual = session.toolFrame(tool: tool, animation: animation, seconds: frame["time"] as! Double, reduced: false)
            #expect(actual == expected)
            #expect(session.toolFrame(tool: tool, animation: animation, seconds: 10, reduced: true).nodes == actual.nodes)
        }
    }
}

@Test func backgroundBotRendererSettlesAndRestarts() async {
    let renderer = SuzentBotRenderer()
    var settled = false
    for index in 0..<150 {
        let frame = await renderer.frame(pending: false, error: false, thinking: false, tool: nil, active: false,
            time: Double(index) * 33.4, reduced: false, dark: false)
        if frame.settled { settled = true; break }
    }
    #expect(settled)
    let resumed = await renderer.frame(pending: false, error: false, thinking: true, tool: nil, active: true,
        time: 5100, reduced: false, dark: false)
    #expect(!resumed.settled)
    let reduced = await renderer.frame(pending: true, error: false, thinking: false, tool: nil, active: true,
        time: 5133, reduced: true, dark: true)
    #expect(reduced.settled)
    #expect(reduced.nodes != resumed.nodes)
}
@Test func sharedRendererKeepsEachGlyphsSpringsApart() async {
    let renderer = SuzentBotRenderer()
    let first = await renderer.openGlyph(), second = await renderer.openGlyph()
    for step in 1...15 {
        _ = await renderer.toolFrame(glyph: first, tool: "grep_search", animation: "radar", seconds: Double(step) / 30, reduced: false)
    }
    let alone = SuzentBotSession().toolFrame(tool: "grep_search", animation: "radar", seconds: 0.1, reduced: false)
    #expect(await renderer.toolFrame(glyph: second, tool: "grep_search", animation: "radar", seconds: 0.1, reduced: false) == alone)
    await renderer.closeGlyph(first)
    let bot = await renderer.openBot()
    let frame = await renderer.frame(bot: bot, pending: false, error: false, thinking: true, tool: nil, active: true,
        time: 0, reduced: false, dark: false)
    #expect(!frame.nodes.isEmpty)
    await renderer.closeBot(bot)
}
#endif
