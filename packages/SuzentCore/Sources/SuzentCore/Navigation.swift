import Foundation

public struct ChatPageQuery: Hashable, Sendable {
    public var kind: String
    public var value: String
    public init(_ kind: String = "recent", value: String = "") { self.kind = kind; self.value = value }
}

public struct ChatPage: Decodable, Sendable {
    public var chats: [Chat]
    public var total: Int
    public var nextOffset: Int?
    public init(chats: [Chat], total: Int, nextOffset: Int?) {
        self.chats = chats; self.total = total; self.nextOffset = nextOffset
    }
    public func appending(_ page: ChatPage) -> ChatPage {
        let incoming = Set(page.chats.map(\.id))
        return ChatPage(chats: chats.filter { !incoming.contains($0.id) } + page.chats,
                        total: page.total, nextOffset: page.nextOffset)
    }
}

public struct NavigationMetadata: Decodable, Sendable {
    public let regent: Chat?
    public let projects: [Project]
    public init(regent: Chat?, projects: [Project]) { self.regent = regent; self.projects = projects }
}

public struct InitialNavigation: Sendable {
    public let metadata: NavigationMetadata
    public let recent: ChatPage
    public let pinned: ChatPage
    public var chats: [Chat] { (metadata.regent.map { [$0] } ?? []) + pinned.chats + recent.chats }
}

public func localChatPage(_ chats: [Chat], query: ChatPageQuery, offset: Int, limit: Int) -> ChatPage {
    let rows = chats.filter { chat in
        guard !chat.isRegent else { return false }
        if query.kind == "search" { return chat.title.localizedCaseInsensitiveContains(query.value) }
        guard !chat.isScheduled else { return false }
        if query.kind == "pinned" { return chat.pinned == true }
        if chat.pinned == true { return false }
        return query.kind != "project" || chat.projectId == query.value
    }
    let page = Array(rows.dropFirst(offset).prefix(limit))
    let next = offset + page.count
    return ChatPage(chats: page, total: rows.count, nextOffset: next < rows.count ? next : nil)
}

public extension MobileClient {
    func chatPage(_ query: ChatPageQuery, offset: Int = 0, limit: Int = 30) async throws -> ChatPage {
        localChatPage(try await chats(), query: query, offset: offset, limit: limit)
    }
    func navigationMetadata() async throws -> NavigationMetadata {
        let rows = try await chats()
        let projects = try await projects().map { project in
            Project(id: project.id, name: project.name,
                    chatCount: rows.filter { $0.projectId == project.id && !$0.isRegent && !$0.isScheduled && $0.pinned != true }.count)
        }
        return NavigationMetadata(regent: rows.first { $0.isRegent }, projects: projects)
    }
    func chatStatuses(_ ids: [String]) async throws -> [Chat] {
        let allowed = Set(ids)
        return try await chats().filter { allowed.contains($0.id) }
    }
    func initialNavigation() async throws -> InitialNavigation {
        let metadata = try await navigationMetadata()
        let recent = try await chatPage(ChatPageQuery(), offset: 0, limit: 30)
        let pinned = try await chatPage(ChatPageQuery("pinned"), offset: 0, limit: 30)
        return InitialNavigation(metadata: metadata, recent: recent, pinned: pinned)
    }
}
