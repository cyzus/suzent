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
