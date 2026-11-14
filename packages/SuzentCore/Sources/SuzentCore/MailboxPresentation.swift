import Foundation

public struct MailboxPresentation: Decodable, Sendable, Equatable {
    public let threadKey: String?
    public let title: String
    public let source: String
    public let context: String?
    public let icon: String
    public let activity: String?
    public let detail: String?
}

public extension MailboxItem {
    var display: MailboxPresentation {
        presentation ?? MailboxPresentation(threadKey: nil, title: summary, source: source, context: nil, icon: "inbox", activity: nil, detail: nil)
    }
}

public struct MailboxThread: Identifiable, Sendable {
    public let id: String
    public let items: [MailboxItem]
    public var latest: MailboxItem { items[0] }
    public var unreadIds: [Int] { items.filter(\.unread).map(\.id) }
}

public func mailboxThreads(_ items: [MailboxItem]) -> [MailboxThread] {
    var groups: [String: [MailboxItem]] = [:]
    var order: [String] = []
    var seen: Set<Int> = []
    for item in items.sorted(by: { $0.id > $1.id }) where seen.insert(item.id).inserted {
        let key = item.presentation?.threadKey.flatMap { $0.isEmpty ? nil : $0 } ?? "item:\(item.id)"
        if groups[key] == nil { order.append(key) }
        groups[key, default: []].append(item)
    }
    return order.map { MailboxThread(id: $0, items: groups[$0]!) }
}
