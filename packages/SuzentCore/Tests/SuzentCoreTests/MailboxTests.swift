import Foundation
import Testing
@testable import SuzentCore

@Test func mailboxUsesServerUnreadCountAndDistinguishesEventsFromNotifications() throws {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/mailbox-fixture.json"))
    let page = try JSONDecoder().decode(MailboxPage.self, from: data)
    #expect(page.unread == 7)
    #expect(page.hasMore)
    #expect(page.items.map(\.unread) == [true, false, false])
    #expect(page.items[0].chatId == nil)
    #expect(page.items[1].chatId == "shared")
}

@Test func legacyDesktopDoesNotAdvertiseMailbox() throws {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let data = Data(#"{"device":{"device_id":"phone","display_name":"Phone","platform":"ios","permissions":{"chat_ids":[],"all_chats":true,"create_chats":false,"send":false,"stop":false}},"client_protocol":1,"stream_protocols":[1]}"#.utf8)
    #expect(try decoder.decode(ClientSession.self, from: data).mailbox == nil)
}

@Test func mailboxUsesBackendThreadKeysAndPresentation() throws {
    struct Fixture: Decodable { let presentation: MailboxPresentation }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/mailbox-thread-fixtures.json"))
    let fixtures = try JSONDecoder().decode([Fixture].self, from: data)
    #expect(!fixtures.isEmpty)
    let first = MailboxItem(id: 1, source: "any-webhook", eventType: "event", summary: "Old subject", payload: "{}", status: "notified", chatId: nil, createdAt: "2026-11-14T00:00:00Z", readAt: nil, presentation: fixtures[0].presentation)
    let latest = MailboxItem(id: 6, source: "any-webhook", eventType: "other", summary: "New subject", payload: "{}", status: "notified", chatId: nil, createdAt: "2026-11-14T00:00:00Z", readAt: "read", presentation: fixtures[0].presentation)
    let threads = mailboxThreads([first, latest, latest])
    #expect(threads.count == 1)
    #expect(threads[0].items.map(\.id) == [6, 1])
    #expect(threads[0].unreadIds == [1])
    #expect(first.display.title == fixtures[0].presentation.title)
    var legacy = first; legacy.presentation = nil
    var other = latest; other.presentation = nil
    #expect(mailboxThreads([legacy, other]).count == 2)
    #expect(legacy.display.title == "Old subject")
}

@Test func continuousMailboxDeduplicatesOverlappingPagesAndStopsAtEnd() async throws {
    let event: @Sendable (Int) -> MailboxItem = { id in
        MailboxItem(id: id, source: "github", eventType: "issues.opened", summary: "Title", payload: "{}", status: "notified", chatId: nil, createdAt: "2026-11-14T00:00:00Z", readAt: nil)
    }
    actor Calls {
        var offsets: [Int] = []
        func record(_ offset: Int) { offsets.append(offset) }
    }
    let calls = Calls()
    let result = try await mailboxWindow(lastOffset: 100) { offset in
        await calls.record(offset)
        return offset == 0 ? MailboxPage(items: [event(3), event(2)], unread: 7, hasMore: true)
            : MailboxPage(items: [event(2), event(1)], unread: 6, hasMore: false)
    }
    #expect(await calls.offsets == [0, 50])
    #expect(result.items.map(\.id) == [3, 2, 1])
    #expect(result.unread == 6)
    #expect(!result.hasMore)
}
