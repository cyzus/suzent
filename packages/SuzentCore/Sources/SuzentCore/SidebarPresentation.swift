import Foundation

public extension Chat {
    var isSubagent: Bool { platform?.lowercased() == "subagent" }
    var isScheduled: Bool { platform?.lowercased() == "cron" }
}

public struct SidebarChatEntry: Identifiable, Sendable {
    public let chat: Chat
    public let depth: Int
    public let childCount: Int
    public var id: String { chat.id }
}

public func scheduledChatIDs(_ chats: [Chat]) -> Set<String> {
    let byID = Dictionary(chats.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
    return Set(chats.filter { chat in
        var current: Chat? = chat
        var seen = Set<String>()
        while let item = current, seen.insert(item.id).inserted {
            if item.isScheduled { return true }
            current = item.isSubagent ? byID[item.parentChatId ?? ""] : nil
        }
        return false
    }.map(\.id))
}

public func sidebarChats(_ chats: [Chat], search: String, expanded: Set<String>) -> [SidebarChatEntry] {
    let byID = Dictionary(chats.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
    let order = Dictionary(chats.enumerated().map { ($0.element.id, $0.offset) }, uniquingKeysWith: { first, _ in first })
    func root(_ chat: Chat) -> String {
        var current = chat
        var path: [String] = []
        while true {
            if let cycle = path.firstIndex(of: current.id) {
                return path[cycle...].min(by: { order[$0, default: 0] < order[$1, default: 0] }) ?? current.id
            }
            path.append(current.id)
            guard current.isSubagent, let parent = byID[current.parentChatId ?? ""] else { return current.id }
            current = parent
        }
    }
    let roots = Dictionary(chats.map { ($0.id, root($0)) }, uniquingKeysWith: { first, _ in first })
    let children = Dictionary(grouping: chats.filter { roots[$0.id] != $0.id }, by: { roots[$0.id] ?? $0.id })
    let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
    var result: [SidebarChatEntry] = []
    for chat in chats where roots[chat.id] == chat.id {
        let descendants = children[chat.id] ?? []
        let matches = descendants.filter { query.isEmpty || $0.title.localizedCaseInsensitiveContains(query) }
        guard query.isEmpty || chat.title.localizedCaseInsensitiveContains(query) || !matches.isEmpty else { continue }
        result.append(SidebarChatEntry(chat: chat, depth: 0, childCount: descendants.count))
        if !query.isEmpty || expanded.contains(chat.id) {
            for child in matches { result.append(SidebarChatEntry(chat: child, depth: 1, childCount: 0)) }
        }
    }
    return result
}
