import Testing
@testable import SuzentCore

@Test func everyRobotVariantDrawsFiniteMarks() {
    for variant in RobotVariant.allCases {
        for seconds in [0, 0.37, 1.9, 7.25] {
            let marks = RobotScene.frame(variant, seconds: seconds)
            #expect(!marks.isEmpty, "\(variant)")
            for case let .shape(points, _, _, _) in marks {
                #expect(points.allSatisfy { $0.x.isFinite && $0.y.isFinite }, "\(variant)")
            }
        }
    }
}

@Test func idleRobotSitsInTheMiddleOfItsSlotAndPeekerStartsHidden() {
    guard case let .shape(idle, _, _, _) = RobotScene.frame(.idle, seconds: 0)[0],
          case let .shape(peeker, _, _, _) = RobotScene.frame(.peeker, seconds: 0)[0] else { Issue.record("expected shapes"); return }
    #expect(abs(idle.map(\.x).min()! - 4) < 1e-9)
    #expect(abs(idle.map(\.y).max()! - 28) < 1e-9)
    #expect(peeker.map(\.y).min()! > RobotScene.slot)
    #expect(RobotScene.clips(.peeker))
}

@Test func robotBadgeMoodFollowsDesktop() {
    #expect(robotPersonality(0) == .idle)
    #expect(robotPersonality(0.4) == .observer)
    #expect(robotPersonality(1) == .dj)
    #expect(robotBadgeVariant(base: .idle, startled: true, pending: true, streaming: true, tool: "Read") == .shaker)
    #expect(robotBadgeVariant(base: .idle, startled: false, pending: true, streaming: true, tool: "Read") == .skeptic)
    #expect(robotBadgeVariant(base: .idle, startled: false, pending: false, streaming: true, tool: "Read") == .eater)
    #expect(robotBadgeVariant(base: .idle, startled: false, pending: false, streaming: true, tool: "Bash") == .workout)
    #expect(robotBadgeVariant(base: .love, startled: false, pending: false, streaming: true, tool: nil) == .observer)
    #expect(robotBadgeVariant(base: .love, startled: false, pending: false, streaming: false, tool: nil) == .love)
    let parts = [MessagePart(type: "tool", toolName: "grep_search", output: "done"), MessagePart(type: "tool", toolName: "web_search"), MessagePart(type: "text", text: "Hi")]
    #expect(robotCurrentTool(parts) == "web_search")
    #expect(robotCurrentTool([MessagePart(type: "tool", toolName: "grep_search", output: "done"), MessagePart(type: "text", text: "Hi")]) == nil)
    #expect(!toolCallFailed(MessagePart(type: "tool", toolName: "Bash", state: "error")))
}

@Test func reducedMotionHoldsAVisibleFrameForEveryFace() {
    for variant in RobotVariant.allCases {
        let bodies = RobotScene.frame(variant, seconds: 0, reduced: true).compactMap { mark -> [RobotPoint]? in
            if case let .shape(points, .body, alpha, _) = mark, alpha > 0.9, points.count > 8 { return points }
            return nil
        }
        #expect(bodies.contains { $0.contains { $0.y >= 0 && $0.y <= RobotScene.slot } }, "\(variant)")
    }
}
