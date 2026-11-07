import Foundation

/// The phone's version of the desktop chat side panel.
public struct ChatDetails: Decodable, Sendable {
    public struct PermissionMode: Decodable, Sendable {
        public var mode: String
        public let available: [String]
        public let canChange: Bool
    }

    public struct Context: Decodable, Sendable {
        public let tokens: Int
        public let limit: Int

        public var percent: Int { contextPercent(tokens: tokens, limit: limit) }
    }

    public struct Goal: Decodable, Sendable {
        public let objective: String
        public let status: String
        public let turnsElapsed: Int?
        public let maxTurns: Int?
    }

    public struct PlanTask: Decodable, Identifiable, Sendable {
        public let id: String
        public let title: String
        public let status: String
        public let activeForm: String?
    }

    public struct Agent: Decodable, Identifiable, Sendable {
        public let id: String
        public let description: String
        public let status: String
        public let chatId: String?
        public let startedAt: String?
        public let finishedAt: String?

        public var isActive: Bool { status == "running" || status == "queued" }
    }

    public struct MemoryItem: Decodable, Sendable, Hashable {
        public let content: String
        public let category: String?
    }

    public struct Memory: Decodable, Sendable {
        public let recalled: [MemoryItem]
        public let saved: [MemoryItem]
    }

    public var permissionMode: PermissionMode
    public let context: Context?
    public let goal: Goal?
    public let tasks: [PlanTask]
    public let agents: [Agent]
    public let memory: Memory?
    public let files: Bool
}

public struct WorkspaceEntry: Decodable, Identifiable, Sendable, Hashable {
    public let name: String
    public let isDir: Bool
    public let size: Int
    public let modifiedAt: Double

    public var id: String { name }
}

public struct WorkspaceListing: Decodable, Sendable {
    public let path: String
    public let entries: [WorkspaceEntry]
    public let truncated: Bool
}

public func contextPercent(tokens: Int, limit: Int) -> Int {
    guard limit > 0, tokens > 0 else { return 0 }
    return min(100, max(1, Int((Double(tokens) * 100 / Double(limit)).rounded())))
}

/// Paths are relative to the conversation's project workspace; "" is its root.
public func workspaceChildPath(_ parent: String, _ name: String) -> String {
    parent.isEmpty ? name : "\(parent)/\(name)"
}

public func workspaceParentPath(_ path: String) -> String {
    guard let slash = path.lastIndex(of: "/") else { return "" }
    return String(path[..<slash])
}
