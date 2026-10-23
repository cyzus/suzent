import Foundation

public extension Chat {
    var isSubagent: Bool { platform?.lowercased() == "subagent" }
    var isScheduled: Bool { platform?.lowercased() == "cron" }
}

public struct SidebarChatEntry: Identifiable, Sendable {
    public let chat: Chat
    public let depth: Int
    public let childCount: Int
    public let root: Chat
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
        result.append(SidebarChatEntry(chat: chat, depth: 0, childCount: descendants.count, root: chat))
        if !query.isEmpty || expanded.contains(chat.id) {
            for child in matches { result.append(SidebarChatEntry(chat: child, depth: 1, childCount: 0, root: chat)) }
        }
    }
    return result
}

/// Desktop parity: a failure is resolved once the chat was updated after the run finished.
public extension ScheduledTask {
    var failureHandled: Bool {
        guard hasError, let finished = lastRunFinishedAt, let updated = chatUpdatedAt else { return false }
        guard let finish = SidebarPresentationDate.parse(finished),
              let chat = SidebarPresentationDate.parse(updated) else { return false }
        return chat > finish
    }

    /// True while a failure still needs attention; a handled one stops ranking and reading as failed.
    var unresolvedError: Bool { hasError && !failureHandled }
}

enum SidebarPresentationDate {
    static func parse(_ raw: String) -> Date? {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return parser.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    }
}

/// Desktop automation order: unresolved failures first, then active tasks, then paused
/// ones, each group by next run (tasks without a next run last).
private func scheduledTaskRank(_ task: ScheduledTask) -> Int {
    task.unresolvedError ? 0 : (task.active ? 1 : 2)
}

private func scheduledTaskNextRun(_ task: ScheduledTask) -> TimeInterval {
    guard let raw = task.nextRunAt else { return .greatestFiniteMagnitude }
    let parser = ISO8601DateFormatter()
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let date = parser.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    return date?.timeIntervalSince1970 ?? .greatestFiniteMagnitude
}

public func orderedScheduledTasks(_ tasks: [ScheduledTask]) -> [ScheduledTask] {
    tasks.enumerated()
        .sorted { left, right in
            let leftRank = scheduledTaskRank(left.element)
            let rightRank = scheduledTaskRank(right.element)
            if leftRank != rightRank { return leftRank < rightRank }
            let leftNext = scheduledTaskNextRun(left.element)
            let rightNext = scheduledTaskNextRun(right.element)
            if leftNext != rightNext { return leftNext < rightNext }
            return left.offset < right.offset
        }
        .map(\.element)
}

public struct ScheduledSidebarGroup: Identifiable, Sendable {
    public let task: ScheduledTask?
    public let root: SidebarChatEntry?
    public let children: [SidebarChatEntry]
    public var id: String { task.map { "task:\($0.id)" } ?? "chat:\(root?.id ?? "")" }
}

public func scheduledSidebarGroups(_ chats: [Chat], tasks: [ScheduledTask], search: String, expanded: Set<String>) -> [ScheduledSidebarGroup] {
    let ids = scheduledChatIDs(chats)
    let source = chats.filter { ids.contains($0.id) }
    let allRows = sidebarChats(source, search: "", expanded: expanded)
    let searched = sidebarChats(source, search: search, expanded: expanded)
    let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
    var result: [ScheduledSidebarGroup] = []
    let ordered = orderedScheduledTasks(tasks)
    let taskChatIDs = Set(ordered.compactMap(\.chatId))
    for task in ordered {
        let matches = query.isEmpty || task.name.localizedCaseInsensitiveContains(query)
        let rows = (matches ? allRows : searched).filter { $0.root.id == task.chatId }
        guard matches || !rows.isEmpty else { continue }
        result.append(ScheduledSidebarGroup(task: task, root: rows.first { $0.depth == 0 }, children: rows.filter { $0.depth > 0 }))
    }
    for root in searched where root.depth == 0 && !taskChatIDs.contains(root.id) {
        result.append(ScheduledSidebarGroup(task: nil, root: root, children: searched.filter { $0.root.id == root.id && $0.depth > 0 }))
    }
    return result
}
