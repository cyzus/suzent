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
        XCTAssertFalse(AssemblyScene.frame(seconds: 0.2).contains { [UInt32(0x737980), 0xc4c7ca, 0xa8adb3, 0xe0e2e4].contains($0.color) })
        let scan = AssemblyScene.frame(seconds: 2.2 / 1.45).filter { [UInt32(0x737980), 0xc4c7ca, 0xa8adb3, 0xe0e2e4].contains($0.color) }
        XCTAssertEqual(scan.count, 10)
        XCTAssertTrue(scan.allSatisfy { $0.points.first!.y != $0.points.last!.y })
        XCTAssertFalse(AssemblyScene.frame(seconds: 3.2 / 1.45).contains { [UInt32(0x737980), 0xc4c7ca, 0xa8adb3, 0xe0e2e4].contains($0.color) })
    }
    func testReducedMotionMovesOnlyFinishedRobotsOneSlotAtATime() {
        func xs(_ seconds: Double) -> [Double] { AssemblyScene.frame(seconds: seconds, reduced: true).flatMap { $0.points.map(\.x) } }
        func shadows(_ seconds: Double) -> [AssemblyMark] { AssemblyScene.frame(seconds: seconds, reduced: true).filter { $0.color == 0 } }
        for seconds in [0, 1, 2.2, 2.5] {
            let marks = AssemblyScene.frame(seconds: seconds, reduced: true)
            XCTAssertEqual(marks.filter { $0.color == 0xE8ECEB }.count, shadows(seconds).count * 2)
            XCTAssertFalse(marks.contains { $0.width != 0.65 })
        }
        XCTAssertEqual(xs(1.7), xs(0))
        XCTAssertGreaterThan(shadows(2.2).last!.points[0].x, shadows(0).last!.points[0].x)
        XCTAssertEqual(xs(2.6), xs(0))
    }
    func testFramesStayFiniteAcrossRandomizedCycles() {
        for index in 0...400 {
            for mark in AssemblyScene.frame(seconds: Double(index) / 30) {
                XCTAssertTrue((0...1).contains(mark.alpha))
                XCTAssertTrue(mark.points.allSatisfy { $0.x.isFinite && $0.y.isFinite })
            }
        }
    }

}
