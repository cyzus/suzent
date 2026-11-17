import Testing
@testable import SuzentCore

@Test func botMovesBetweenRailAndReplyWithoutHistoricalBadges() {
    let tool = MessagePart(type: "tool", toolName: "read_file", state: "running")
    #expect(botPlacement([], live: true, latest: true, regent: false) == .assembly)
    #expect(botPlacement([tool], live: true, latest: true, regent: false) == .rail)
    #expect(botPlacement([tool, MessagePart(type: "text", text: "Answer"), MessagePart(type: "citation-sources")], live: true, latest: true, regent: false) == .footer)
    #expect(botPlacement([tool], live: false, latest: true, regent: false) == .footer)
    #expect(botPlacement([tool], live: false, latest: false, regent: false) == .none)
    let pending = MessagePart(type: "tool", toolName: "read_file", state: "approval-requested")
    #expect(botPlacement([pending], live: false, latest: false, regent: false) == .rail)
    #expect(botPlacement([pending], live: true, latest: true, regent: true) == .none)
}
