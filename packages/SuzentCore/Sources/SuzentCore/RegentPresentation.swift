import Foundation

private let regentReactions: Set<String> = ["👍", "❤️", "👀", "✅", "🎉", "😂", "🤔", "🙏", ""]

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
        if part.type == "text", isQuietReply(text) || (live && !text.isEmpty && "HEARTBEAT_OK".hasPrefix(text)) { return [] }
        if part.toolName == "send_message", let texts = regentMetadata(part)?["regent_messages"] as? [String],
           !texts.isEmpty, texts.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) {
            return texts.enumerated().compactMap { index, text in
                if isQuietReply(text) { return nil }
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
        // Background wake-ups, including a reply that carries its trigger, must never react to an earlier user turn.
        if ["system_triggered", "trigger"].contains(row.role) || !row.triggers.isEmpty { userIndex = nil }
        if let index = userIndex, let reaction = regentReaction(row.parts) { result[index].reaction = reaction }
        let parts = regentDisplayParts(row.parts)
        if !parts.isEmpty {
            var shown = row
            shown.parts = parts
            result.append(shown)
        } else if !row.triggers.isEmpty {
            result.append(DisplayMessage(role: "system_triggered", parts: [], citationSources: row.citationSources,
                                         timestamp: row.timestamp, messageIndex: row.messageIndex, triggers: row.triggers))
        }
    }
    if let index = userIndex, let reaction = regentReaction(liveParts) { result[index].reaction = reaction }
    return result
}
