import Foundation
import Testing
@testable import SuzentCore

@Test @MainActor func demoNavigationPagesSearchAndPinsIndependently() async throws {
    let client = try DemoClient(language: "en")
    for index in 0..<35 { _ = try await client.createChat(title: "Page \(index)", projectID: "demo-home") }
    let initial = try await client.initialNavigation()
    #expect(initial.recent.chats.count == 30)
    #expect(initial.recent.nextOffset == 30)
    #expect(initial.pinned.chats.map(\.id) == ["demo-welcome"])
    #expect(initial.metadata.regent?.isRegent == true)
    let second = try await client.chatPage(ChatPageQuery(), offset: 30, limit: 30)
    #expect(second.nextOffset == nil)
    #expect(Set(initial.recent.chats.map(\.id)).isDisjoint(with: second.chats.map(\.id)))
    let search = try await client.chatPage(ChatPageQuery("search", value: "unavailable"), offset: 0, limit: 30)
    #expect(search.chats.map(\.id) == ["demo-failure"])
    #expect(initial.metadata.projects.first { $0.id == "demo-home" }?.chatCount == 39)
}

@Test func appendedPagesDeduplicateUpdatedRows() {
    let first = ChatPage(chats: [Chat(id: "a", title: "Old"), Chat(id: "b", title: "B")], total: 3, nextOffset: 2)
    let next = ChatPage(chats: [Chat(id: "a", title: "New"), Chat(id: "c", title: "C")], total: 3, nextOffset: nil)
    let merged = first.appending(next)
    #expect(Set(merged.chats.map(\.id)).count == 3)
    #expect(merged.chats.first { $0.id == "a" }?.title == "New")
    #expect(merged.nextOffset == nil)
}

@Test func paginationCapabilityAndWireMetadataDecode() throws {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let session = try decoder.decode(ClientSession.self, from: Data(#"""
    {"client_protocol":1,"stream_protocols":[1],"chat_pagination":1,"device":{"device_id":"phone","display_name":"Phone","platform":"ios","permissions":{"chat_ids":[],"all_chats":true,"create_chats":true,"send":true,"stop":true}}}
    """#.utf8))
    #expect(session.chatPagination == 1)
    let metadata = try JSONDecoder().decode(NavigationMetadata.self, from: Data(#"{"regent":null,"projects":[{"id":"p","name":"Project","chatCount":1005}]}"#.utf8))
    #expect(metadata.projects.first?.chatCount == 1005)
    let page = try JSONDecoder().decode(ChatPage.self, from: Data(#"{"chats":[],"total":1005,"nextOffset":30}"#.utf8))
    #expect(page.nextOffset == 30)
}
