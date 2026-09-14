import Foundation

public struct MessagePart: Decodable, Sendable {
    public let type: String
    public let text: String?
    public let toolName: String?
    public let args: String?
    public let output: String?
    public let toolCallId: String?
    public let state: String?
}

public struct DisplayMessage: Sendable {
    public let role: String
    public let text: String
    public let activities: [MessagePart]
}

public func presentMessages(_ messages: [ChatMessage]) -> [DisplayMessage] {
    let represented = Set(messages.flatMap { $0.parts }.filter { $0.type == "tool" }
        .compactMap(\.toolCallId).filter { !$0.isEmpty })
    return messages.compactMap { message in
        if PresentationTokens.compactionSummaryMarkers.contains(where: { message.content.contains($0) }) { return nil }
        if message.role == "tool", let id = message.toolCallId, represented.contains(id) { return nil }
        let parts = message.role == "tool"
            ? [MessagePart(type: "tool", text: nil, toolName: message.name, args: nil,
                           output: message.content, toolCallId: message.toolCallId, state: nil)] : message.parts
        let textParts = parts.filter { $0.type == "text" }
        let text = !textParts.isEmpty ? textParts.compactMap(\.text).joined(separator: "\n\n")
            : parts.isEmpty ? message.content : ""
        let activities = parts.filter { $0.type != "text" && !($0.type == "tool" &&
            PresentationTokens.ignoredToolNames.contains(($0.toolName ?? "").lowercased())) }
        return text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && activities.isEmpty
            ? nil : DisplayMessage(role: message.role, text: text, activities: activities)
    }
}
