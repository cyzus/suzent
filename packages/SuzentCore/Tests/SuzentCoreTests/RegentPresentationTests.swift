import Foundation
import Testing
@testable import SuzentCore

@Test func sharedRegentDeliveryContract() throws {
    struct Fixture: Decodable {
        let name: String
        let parts: [MessagePart]
        let texts: [String]
        let activities: Int
        let reaction: String?
        let live: Bool
    }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/regent-fixtures.json"))
    for fixture in try JSONDecoder().decode([Fixture].self, from: data) {
        let parts = regentDisplayParts(fixture.parts, live: fixture.live)
        #expect(parts.filter { $0.type == "text" }.compactMap(\.text) == fixture.texts, "\(fixture.name)")
        #expect(parts.filter { $0.type != "text" }.count == fixture.activities, "\(fixture.name)")
        #expect(regentReaction(fixture.parts) == fixture.reaction, "\(fixture.name)")
    }
}

@Test func regentReactionsStayWithTheirUserTurn() throws {
    let reaction = MessagePart(type: "tool", toolName: "react_to_message", output: #"{"success":true,"metadata":{"regent_reaction":"✅"}}"#, toolCallId: "reaction", state: "completed")
    let user = DisplayMessage(role: "user", parts: [.init(type: "text", text: "HEARTBEAT_OK")], citationSources: [])
    let rows = regentMessages([user, DisplayMessage(role: "assistant", parts: [reaction], citationSources: [])])
    #expect(rows.count == 1)
    #expect(rows.first?.text == "HEARTBEAT_OK")
    #expect(rows.first?.reaction == "✅")
    let background = DisplayMessage(role: "system_triggered", parts: [.init(type: "text", text: "Check-in")], citationSources: [])
    #expect(regentMessages([user, background], liveParts: [reaction]).first?.reaction == nil)
    #expect(regentMessages([user], liveParts: [reaction]).first?.reaction == "✅")
    #expect(regentMessages([user], liveParts: []).first?.reaction == nil)
}

@Test func regentMetadataIsOptionalForOlderBackends() throws {
    let old = try JSONDecoder().decode(Chat.self, from: Data(#"{"id":"old","title":"Old"}"#.utf8))
    #expect(!old.isRegent && old.regent == nil)
    let regent = try JSONDecoder().decode(Chat.self, from: Data(#"{"id":"focal-suzent","title":"Regent","platform":"focal","regent":{"waiting":2,"unread":1}}"#.utf8))
    #expect(regent.isRegent && regent.regent?.waiting == 2)
}
