import Foundation

public struct CitationSource: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public let type: String
    public let title: String
    public let url: String?
    public let snippet: String?
    public let favicon: String?
}

public struct MessagePart: Decodable, Sendable, Equatable {
    public var type: String
    public var text: String?
    public var toolName: String?
    public var args: String?
    public var output: String?
    public var toolCallId: String?
    public var state: String?
    public var messageId: String?
    public var citationSources: [CitationSource]?
    public init(type: String, text: String? = nil, toolName: String? = nil, args: String? = nil,
                output: String? = nil, toolCallId: String? = nil, state: String? = nil, messageId: String? = nil,
                citationSources: [CitationSource]? = nil) {
        self.type = type; self.text = text; self.toolName = toolName; self.args = args
        self.output = output; self.toolCallId = toolCallId; self.state = state; self.messageId = messageId
        self.citationSources = citationSources
    }

}

public struct DisplayMessage: Sendable {
    public let role: String
    public let parts: [MessagePart]
    public let citationSources: [CitationSource]
    public var model: String? = nil
    public var timestamp: String? = nil
    public var messageIndex: Int = 0
    public var text: String { parts.filter { $0.type == "text" }.compactMap(\.text).joined(separator: "\n\n") }
}

public func presentMessages(_ messages: [ChatMessage], liveToolIds: Set<String> = []) -> [DisplayMessage] {
    let indexedSources = messages.enumerated().flatMap { index, message in
        message.parts.flatMap { part in (part.citationSources ?? []).map { (index, $0) } }
    }
    let represented = Set(messages.flatMap { $0.parts }.filter { $0.type == "tool" }
        .compactMap(\.toolCallId).filter { !$0.isEmpty })
    let rows: [DisplayMessage] = messages.enumerated().compactMap { messageIndex, message in
        if PresentationTokens.compactionSummaryMarkers.contains(where: { message.content.contains($0) }) { return nil }
        if message.role == "tool", let id = message.toolCallId, (represented.contains(id) || liveToolIds.contains(id)) { return nil }
        let rawParts: [MessagePart]
        if message.role == "tool" {
            rawParts = [MessagePart(type: "tool", toolName: message.name, output: message.content, toolCallId: message.toolCallId)]
        } else if message.parts.isEmpty {
            rawParts = [MessagePart(type: "text", text: message.content)]
        } else {
            rawParts = message.parts.filter { $0.type != "tool" || !liveToolIds.contains($0.toolCallId ?? "") }
        }
        let parts = normalizeParts(rawParts)
        let localSources = rawParts.flatMap { $0.citationSources ?? [] }
        let referencedIDs = Set(parts.flatMap { citationSourceIDs($0.text ?? "") })
        let nearbySources = referencedIDs.compactMap { id in
            indexedSources.filter { $0.1.id == id }.min { abs($0.0 - messageIndex) < abs($1.0 - messageIndex) }?.1
        }
        let sources = (localSources + nearbySources).reduce(into: [CitationSource]()) { sources, source in
            if !sources.contains(where: { $0.id == source.id }) { sources.append(source) }
        }
        return parts.isEmpty ? nil : DisplayMessage(role: message.role, parts: parts, citationSources: sources, model: message.model, timestamp: message.timestamp, messageIndex: messageIndex)
    }
    var grouped: [DisplayMessage] = []
    for row in rows {
        // Store rows within a turn share one badge and footer, including the final text.
        if let previous = grouped.last,
           ["assistant", "tool"].contains(previous.role), ["assistant", "tool"].contains(row.role) {
            grouped[grouped.count - 1] = DisplayMessage(
                role: previous.role == "assistant" || row.role == "assistant" ? "assistant" : "tool",
                parts: normalizeParts(previous.parts + row.parts),
                citationSources: (previous.citationSources + row.citationSources).reduce(into: [CitationSource]()) { sources, source in
                    if !sources.contains(where: { $0.id == source.id }) { sources.append(source) }
                },
                model: row.model ?? previous.model, timestamp: row.timestamp ?? previous.timestamp, messageIndex: row.messageIndex)
        } else { grouped.append(row) }
    }
    return grouped
}

public func normalizeParts(_ parts: [MessagePart]) -> [MessagePart] {
    var result: [MessagePart] = []
    for part in parts {
        if part.type == "citation-sources" { continue }
        if ["text", "reasoning"].contains(part.type), (part.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { continue }
        if part.type == "tool", PresentationTokens.ignoredToolNames.contains((part.toolName ?? "").lowercased()) { continue }
        if part.type == "tool", let id = part.toolCallId, !id.isEmpty,
           let index = result.firstIndex(where: { $0.type == "tool" && $0.toolCallId == id }) {
            var merged = part
            if (merged.toolName ?? "").isEmpty { merged.toolName = result[index].toolName }
            if (merged.args ?? "").isEmpty { merged.args = result[index].args }
            if (merged.output ?? "").isEmpty { merged.output = result[index].output }
            if (merged.state ?? "").isEmpty { merged.state = result[index].state }
            result[index] = merged
        } else { result.append(part) }
    }
    return result
}

/// Groups parts already normalized at the history or live-publication boundary.
public func activityChunks(_ parts: [MessagePart]) -> [[MessagePart]] {
    var chunks: [[MessagePart]] = []
    for part in parts {
        if part.type == "text" || chunks.isEmpty || chunks.last?.last?.type == "text" { chunks.append([part]) }
        else { chunks[chunks.count - 1].append(part) }
    }
    return chunks
}

public struct LiveActivityBuffer: Sendable {
    private var parts: [MessagePart] = []
    private var textId = ""
    private var reasonIndex: Int?
    private var startedArgs: Set<String> = []
    private var dirty = false
    public init() {}
    public mutating func drain() -> [MessagePart]? {
        guard dirty else { return nil }; dirty = false; return normalizeParts(parts)
    }
    public mutating func consume(_ event: StreamEvent) {
        let fields = event.fields
        let id = fields["toolCallId"]?.text ?? ""
        let delta = event.delta ?? ""
        switch event.type {
        case "STREAM_RESET": parts = []; startedArgs = []; reasonIndex = nil; textId = ""
        case "TEXT_MESSAGE_START":
            textId = fields["messageId"]?.text ?? ""
            parts.append(MessagePart(type: "text", text: "", messageId: textId))
        case "TEXT_MESSAGE_CONTENT":
            let messageId = fields["messageId"]?.text ?? textId
            if let index = parts.lastIndex(where: { $0.type == "text" && $0.messageId == messageId }) { parts[index].text = (parts[index].text ?? "") + delta }
            else { parts.append(MessagePart(type: "text", text: delta, messageId: messageId)) }
        case "THINKING_START", "THINKING_TEXT_MESSAGE_START", "REASONING_START", "REASONING_MESSAGE_START":
            if reasonIndex == nil { reasonIndex = parts.count; parts.append(MessagePart(type: "reasoning", text: "", state: "running")) }
        case "THINKING_TEXT_MESSAGE_CONTENT", "REASONING_MESSAGE_CONTENT", "REASONING_MESSAGE_CHUNK":
            if reasonIndex == nil { reasonIndex = parts.count; parts.append(MessagePart(type: "reasoning", text: "", state: "running")) }
            if let index = reasonIndex { parts[index].text = (parts[index].text ?? "") + delta }
        case "THINKING_END", "THINKING_TEXT_MESSAGE_END", "REASONING_END", "REASONING_MESSAGE_END":
            if let index = reasonIndex { parts[index].state = "completed" }; reasonIndex = nil
        case "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_RESULT":
            guard !id.isEmpty else { return }
            let index = toolIndex(id)
            switch event.type {
            case "TOOL_CALL_START": startedArgs.remove(id); parts[index].toolName = fields["toolCallName"]?.text; parts[index].state = "running"
            case "TOOL_CALL_ARGS":
                if startedArgs.insert(id).inserted { parts[index].args = "" }
                parts[index].args = (parts[index].args ?? "") + delta
            default: parts[index].output = (fields["content"] ?? fields["output"] ?? fields["result"])?.text; parts[index].state = "completed"
            }
        case "CUSTOM":
            guard let value = fields["value"], let toolId = value["toolCallId"]?.text, !toolId.isEmpty else { return }
            switch fields["name"]?.text {
            case "tool_approval_request":
                let index = toolIndex(toolId)
                parts[index].toolName = value["toolName"]?.text; parts[index].args = value["args"]?.text; parts[index].state = "approval-requested"
            case "tool_approval_result":
                let index = toolIndex(toolId); parts[index].output = (value["output"] ?? value["content"] ?? value["result"])?.text; parts[index].state = value["status"]?.text == "executed" ? "completed" : "error"
            default: return
            }
        default: return
        }
        dirty = true
    }
    private mutating func toolIndex(_ id: String) -> Int {
        if let index = parts.firstIndex(where: { $0.type == "tool" && $0.toolCallId == id }) { return index }
        parts.append(MessagePart(type: "tool", toolCallId: id, state: "running")); return parts.count - 1
    }
}

public func streamingMarkdown(_ text: String, active: Bool) -> String {
    guard active, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return text }
    let lastLine = text.split(separator: "\n", omittingEmptySubsequences: false).last?.trimmingCharacters(in: .whitespaces) ?? ""
    let blockEnding = lastLine.hasPrefix("```") || lastLine.hasPrefix("~~~") || lastLine.contains("|")
    return text + (blockEnding ? "\n\n▍" : " ▍")
}

public func showAssemblyBadge(_ parts: [MessagePart], streaming: Bool) -> Bool {
    streaming && !parts.contains {
        $0.type != "text" || !($0.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}
