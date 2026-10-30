import Foundation

private let regentReactions: Set<String> = ["👍", "❤️", "👀", "✅", "🎉", "😂", "🤔", "🙏", ""]

private func isQuietRegentReply(_ text: String) -> Bool {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    let token = "HEARTBEAT_OK"
    let aside: String
    if trimmed.hasPrefix(token) { aside = String(trimmed.dropFirst(token.count)) }
    else if trimmed.hasSuffix(token) { aside = String(trimmed.dropLast(token.count)) }
    else { return false }
    return aside.trimmingCharacters(in: .whitespacesAndNewlines).utf16.count <= 300
}

private func regentMetadata(_ part: MessagePart) -> [String: Any]? {
    guard part.type == "tool", part.state == "completed" || part.state == nil,
          part.outcome == nil,
          let data = part.output?.data(using: .utf8),
          let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          result["success"] as? Bool == true else { return nil }
    return result["metadata"] as? [String: Any]
}

public func regentReaction(_ parts: [MessagePart]) -> String? {
    var reaction: String?
    for part in normalizeParts(parts) where part.toolName == "react_to_message" {
        if let emoji = regentMetadata(part)?["regent_reaction"] as? String, regentReactions.contains(emoji) { reaction = emoji }
    }
    return reaction
}

public func regentDisplayParts(_ parts: [MessagePart], live: Bool = false) -> [MessagePart] {
    normalizeParts(parts).flatMap { part -> [MessagePart] in
        let text = (part.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if part.type == "text", isQuietRegentReply(text) || (live && !text.isEmpty && "HEARTBEAT_OK".hasPrefix(text)) { return [] }
        if part.toolName == "send_message", let texts = regentMetadata(part)?["regent_messages"] as? [String],
           !texts.isEmpty, texts.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) {
            return texts.enumerated().compactMap { index, text in
                if isQuietRegentReply(text) { return nil }
                var bubble = MessagePart(type: "text", text: text, messageId: "\(part.toolCallId ?? ""):\(index)")
                bubble.regentBubble = true
                return bubble
            }
        }
        if part.toolName == "react_to_message", regentReaction([part]) != nil { return [] }
        if ["send_message", "react_to_message"].contains(part.toolName ?? ""), part.state == "running", (part.output ?? "").isEmpty { return [] }
        return [part]
    }
}

public func regentMessages(_ rows: [DisplayMessage], liveParts: [MessagePart] = []) -> [DisplayMessage] {
    var result: [DisplayMessage] = []
    var userIndex: Int?
    for row in rows {
        if row.role == "user" { userIndex = result.count; result.append(row); continue }
        // Background wake-ups must never react to an earlier user turn.
        if ["system_triggered", "trigger"].contains(row.role) { userIndex = nil }
        if let index = userIndex, let reaction = regentReaction(row.parts) { result[index].reaction = reaction }
        let parts = regentDisplayParts(row.parts)
        if !parts.isEmpty {
            result.append(DisplayMessage(role: row.role, parts: parts, citationSources: row.citationSources,
                                         model: row.model, timestamp: row.timestamp, messageIndex: row.messageIndex, files: row.files, workedSeconds: row.workedSeconds, firstMessageIndex: row.firstMessageIndex))
        }
    }
    if let index = userIndex, let reaction = regentReaction(liveParts) { result[index].reaction = reaction }
    return result
}
