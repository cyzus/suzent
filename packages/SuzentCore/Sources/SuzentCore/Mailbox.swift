import Foundation

public struct MailboxItem: Decodable, Identifiable, Sendable, Equatable {
    public let id: Int
    public let source: String
    public let eventType: String
    public let summary: String
    public let payload: String
    public let status: String
    public let chatId: String?
    public let createdAt: String
    public let readAt: String?
    public var presentation: MailboxPresentation? = nil
    public var unread: Bool { status == "notified" && readAt == nil }
}

public struct MailboxPage: Decodable, Sendable {
    public let items: [MailboxItem]
    public let unread: Int
    public let hasMore: Bool
    public static let empty = MailboxPage(items: [], unread: 0, hasMore: false)
}

public func mailboxWindow(lastOffset: Int, fetch: @Sendable (Int) async throws -> MailboxPage) async throws -> MailboxPage {
    var items: [MailboxItem] = []
    var seen: Set<Int> = []
    var page = MailboxPage.empty
    for offset in stride(from: 0, through: lastOffset, by: 50) {
        page = try await fetch(offset)
        items.append(contentsOf: page.items.filter { seen.insert($0.id).inserted })
        if !page.hasMore { break }
    }
    return MailboxPage(items: items, unread: page.unread, hasMore: page.hasMore)
}
