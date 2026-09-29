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
        #expect(rows.map { $0.parts.filter { $0.type != "text" }.count } == fixture.activities, "\(fixture.name)")
    }
}

@Test func sharedActivityReplayContract() throws {
    struct Fixture: Decodable {
        let name: String
        let events: [StreamEvent]
        let types: [String]
        let chunks: [Int]
        let args: [String]
        let outputs: [String]
        let texts: [String]
        let states: [String]
    }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/activity-fixtures.json"))
    for fixture in try JSONDecoder().decode([Fixture].self, from: data) {
        var buffer = LiveActivityBuffer()
        for event in fixture.events { buffer.consume(event) }
        let snapshot = buffer.drain()
        let parts = try #require(snapshot)
        #expect(parts.map(\.type) == fixture.types, "\(fixture.name)")
        #expect(parts.map { $0.args ?? "" } == fixture.args)
        #expect(parts.map { $0.output ?? "" } == fixture.outputs)
        #expect(parts.map { $0.text ?? "" } == fixture.texts)
        #expect(parts.map { $0.state ?? "" } == fixture.states)
        #expect(activityChunks(parts).map(\.count) == fixture.chunks)
        let next = buffer.drain()
        #expect(next == nil)
    }
}

@Test func batchesDeltasAndFlushesFinalChunk() {
    var buffer = LiveActivityBuffer()
    for _ in 0..<100 { buffer.consume(StreamEvent(type: "TEXT_MESSAGE_CONTENT", delta: "a", message: nil)) }
    let batch = buffer.drain()
    #expect(batch?.first?.text == String(repeating: "a", count: 100))
    let idle = buffer.drain()
    #expect(idle == nil)
    buffer.consume(StreamEvent(type: "TEXT_MESSAGE_CONTENT", delta: "尾", message: nil))
    let final = buffer.drain()
    #expect(final?.first?.text == String(repeating: "a", count: 100) + "尾")
    buffer.consume(StreamEvent(type: "STREAM_RESET", delta: nil, message: nil))
    let reset = buffer.drain()
    #expect(reset == [])
}

@Test func resolvesCitationSourcesStoredInAnotherMessage() throws {
    let data = Data(#"[{"role":"assistant","parts":[{"type":"text","text":"Weather \uE200cite\uE202t0_src_1\uE201"}]},{"role":"assistant","parts":[{"type":"citation-sources","citationSources":[{"id":"t0_src_1","type":"webpage","title":"Forecast","url":"https://example.com/weather"}]}]}]"#.utf8)
    let messages = try JSONDecoder().decode([ChatMessage].self, from: data)
    let row = try #require(presentMessages(messages).first)

    #expect(markdownWithCitationLinks(row.text, sources: row.citationSources) == "Weather [Forecast](<https://example.com/weather>)")
}
