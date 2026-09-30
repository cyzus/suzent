import XCTest
@testable import SuzentCore

final class AssemblySceneTests: XCTestCase {
    func testBadgeCollapsesAsSoonAsActivityOrTextAppears() {
        XCTAssertTrue(showAssemblyBadge([], streaming: true))
        XCTAssertTrue(showAssemblyBadge([MessagePart(type: "text", text: " ")], streaming: true))
        XCTAssertFalse(showAssemblyBadge([], streaming: false))
        XCTAssertFalse(showAssemblyBadge([MessagePart(type: "text", text: "hello")], streaming: true))
        XCTAssertFalse(showAssemblyBadge([MessagePart(type: "reasoning")], streaming: true))
        XCTAssertFalse(showAssemblyBadge([MessagePart(type: "tool")], streaming: true))
        XCTAssertFalse(showAssemblyBadge([MessagePart(type: "tool"), MessagePart(type: "text")], streaming: true))
    }

    func testScanFollowsAssemblyAndHasProjectedDepth() {
        XCTAssertFalse(AssemblyScene.frame(seconds: 0.2).contains { $0.color == 0x408DFF })
        let scan = AssemblyScene.frame(seconds: 2.2 / 1.45).filter { $0.color == 0x408DFF }
        XCTAssertEqual(scan.count, 6)
        XCTAssertTrue(scan.allSatisfy { $0.points.first!.y != $0.points.last!.y })
        XCTAssertFalse(AssemblyScene.frame(seconds: 3.2 / 1.45).contains { $0.color == 0x408DFF })
    }
    func testReducedMotionIsStable() {
        let first = AssemblyScene.frame(seconds: 0, reduced: true)
        let later = AssemblyScene.frame(seconds: 100, reduced: true)
        XCTAssertEqual(first.count, later.count)
        XCTAssertEqual(first.flatMap { $0.points.map(\.x) }, later.flatMap { $0.points.map(\.x) })
    }
    func testFramesStayFiniteAcrossRandomizedCycles() {
        for index in 0...400 {
            for mark in AssemblyScene.frame(seconds: Double(index) / 30) {
                XCTAssertTrue((0...1).contains(mark.alpha))
                XCTAssertTrue(mark.points.allSatisfy { $0.x.isFinite && $0.y.isFinite })
            }
        }
    }
    func testCaretOnlyAppearsOnLiveTextAndPreservesFence() {
        XCTAssertEqual(streamingMarkdown("", active: true), "")
        XCTAssertEqual(streamingMarkdown("hello", active: false), "hello")
        XCTAssertEqual(streamingMarkdown("hello", active: true), "hello ▍")
        XCTAssertEqual(streamingMarkdown("```\nx\n```", active: true), "```\nx\n```\n\n▍")
    }
}
