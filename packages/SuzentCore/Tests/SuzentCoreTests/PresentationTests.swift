import Foundation
import Testing
@testable import SuzentCore

@Test func nativePresentationContract() throws {
    struct Fixture: Decodable {
        let name: String
        let messages: [ChatMessage]
        let texts: [String]
        let activities: [Int]
    }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/presentation-fixtures.json"))
    for fixture in try JSONDecoder().decode([Fixture].self, from: data) {
        let rows = presentMessages(fixture.messages)
        #expect(rows.map(\.text) == fixture.texts, "\(fixture.name)")
        #expect(rows.map { $0.activities.count } == fixture.activities, "\(fixture.name)")
    }
}
