import Foundation

/// A message held until its conversation's running turn ends, as Cmd/Ctrl+Enter does on desktop.
public struct QueuedMessage: Sendable, Identifiable, Equatable {
    public let id: UUID
    public let text: String
    public let attachments: [PendingAttachment]

    public init(text: String, attachments: [PendingAttachment] = []) {
        self.id = UUID()
        self.text = text
        self.attachments = attachments
    }
}

/// Each conversation's queued messages, oldest first.
public struct MessageQueues: Sendable, Equatable {
    private var byChat: [String: [QueuedMessage]] = [:]

    public init() {}

    public func of(_ chatID: String?) -> [QueuedMessage] { chatID.flatMap { byChat[$0] } ?? [] }
    public mutating func add(_ item: QueuedMessage, to chatID: String) { byChat[chatID, default: []].append(item) }
    public mutating func remove(_ id: UUID, from chatID: String) { byChat[chatID]?.removeAll { $0.id == id } }
    public mutating func clear(_ chatID: String) { byChat[chatID] = nil }
    public var attachments: [PendingAttachment] { byChat.values.flatMap { $0.flatMap(\.attachments) } }
}

/// The assistant's partial reply, kept on screen when a redirect cuts its turn short.
public func interruptedReply(_ parts: [MessagePart], model: String?) -> ChatMessage? {
    guard !parts.isEmpty else { return nil }
    // As desktop does: a tool cut off mid-run or awaiting approval did not finish.
    let settled = parts.map { part -> MessagePart in
        var part = part
        if part.type == "tool", part.state == "running" || part.state == "approval-requested" { part.state = "error" }
        else if part.state == "running" { part.state = "completed" }
        return part
    }
    let text = settled.filter { $0.type == "text" }.compactMap(\.text).joined(separator: "\n\n")
    return ChatMessage(role: "assistant", content: text, parts: settled, model: model)
}
