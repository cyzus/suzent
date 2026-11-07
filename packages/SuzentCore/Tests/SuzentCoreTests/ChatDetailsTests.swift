import Foundation
import Testing
@testable import SuzentCore

private func chatDetailsFixture() throws -> [String: Any] {
    let url = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("mobile-contract/chat-details-fixtures.json")
    return try #require(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
}

private func decode<T: Decodable>(_ type: T.Type, _ value: Any?) throws -> T {
    try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: try #require(value)))
}

@Test func chatDetailsDecodeTheSharedFixture() throws {
    let fixture = try chatDetailsFixture()
    let details = try decode(ChatDetails.self, fixture["details"])
    #expect(details.permissionMode.mode == "auto")
    #expect(details.permissionMode.canChange)
    #expect(details.context?.percent == 24)
    #expect(details.goal?.objective == "Plan the Kyoto trip")
    #expect(details.tasks.map(\.status) == ["completed", "in_progress", "blocked"])
    #expect(details.agents.map(\.isActive) == [true, false])
    #expect(details.agents[1].chatId == nil)
    #expect(details.memory?.saved.first?.content == "Travelling to Kyoto in April")
    #expect(details.files)

    let minimal = try decode(ChatDetails.self, fixture["minimal"])
    #expect(minimal.context == nil && minimal.goal == nil && minimal.memory == nil)
    #expect(!minimal.files && !minimal.permissionMode.canChange)

    let listing = try decode(WorkspaceListing.self, fixture["files"])
    #expect(listing.path == "uploads")
    #expect(listing.entries.map(\.isDir) == [true, false])
    #expect(listing.entries[1].size == 204800)
}

@Test func chatDetailsSharedHelpers() throws {
    let fixture = try chatDetailsFixture()
    for item in try #require(fixture["contextPercent"] as? [[String: Int]]) {
        #expect(contextPercent(tokens: item["tokens"]!, limit: item["limit"]!) == item["percent"]!)
    }
    #expect(contextPercent(tokens: 10, limit: 0) == 0)
    for item in try #require(fixture["paths"] as? [[String: String]]) {
        let child = workspaceChildPath(item["parent"]!, item["name"]!)
        #expect(child == item["child"]!)
        #expect(workspaceParentPath(child) == item["parent"]!)
    }
}
