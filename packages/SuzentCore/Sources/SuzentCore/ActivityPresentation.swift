import Foundation

public struct RunTiming: Decodable, Sendable, Equatable {
    public let runID: String
    public let startedAt: String
    public let finishedAt: String
    public var activeSeconds: Double?
    public var unknownWait: Bool?
    enum CodingKeys: String, CodingKey {
        case runID = "run_id", startedAt = "started_at", finishedAt = "finished_at"
        case activeSeconds = "active_seconds", unknownWait = "unknown_wait"
    }
}

private func activityDate(_ value: String?) -> Date? {
    guard let value else { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: value) { return date }
    formatter.formatOptions = [.withInternetDateTime]
    return formatter.date(from: value)
}

private func collectedTimings(_ messages: [ChatMessage]) -> [RunTiming] {
    var runs: [String: RunTiming] = [:]
    for message in messages {
        var candidates = message.runTimings
        if candidates.isEmpty, let start = message.runStartedAt, let end = message.runFinishedAt {
            candidates = [RunTiming(runID: message.runID ?? "\(start)/\(end)", startedAt: start, finishedAt: end, activeSeconds: message.runActiveSeconds)]
        }
        for candidate in candidates {
            guard !candidate.runID.isEmpty, let start = activityDate(candidate.startedAt), let end = activityDate(candidate.finishedAt), end >= start else { continue }
            var run = candidate
            let previous = runs[run.runID]
            if run.activeSeconds == nil { run.activeSeconds = run.runID == message.runID ? message.runActiveSeconds ?? previous?.activeSeconds : previous?.activeSeconds }
            run.unknownWait = candidate.unknownWait == true || previous?.unknownWait == true ||
                (run.runID == message.runID && run.activeSeconds == nil && message.parts.contains { $0.toolName == "ask_question" })
            runs[run.runID] = run
        }
    }
    return Array(runs.values)
}

public func hasRecordedTiming(_ messages: [ChatMessage]) -> Bool { !collectedTimings(messages).isEmpty }

public func recordedWorkedSeconds(_ messages: [ChatMessage]) -> Int? {
    let runs = collectedTimings(messages)
    guard !runs.isEmpty, !runs.contains(where: { $0.unknownWait == true && $0.activeSeconds == nil }) else { return nil }
    let seconds = runs.reduce(0.0) { total, run in
        if let active = run.activeSeconds, active.isFinite, active >= 0 { return total + active }
        return total + (activityDate(run.finishedAt)!.timeIntervalSince(activityDate(run.startedAt)!))
    }
    guard seconds.isFinite, seconds >= 0, seconds < Double(Int.max) else { return nil }
    return Int(seconds)
}

public func legacyWorkedSeconds(_ messages: [ChatMessage]) -> [Int: Int] {
    var result: [Int: Int] = [:]
    var boundary: Int?
    var indices: [Int] = []
    func finish() {
        guard let boundary, let start = activityDate(messages[boundary].timestamp) else { return }
        var end: Date?
        for index in indices {
            let message = messages[index]
            let stamp = activityDate(message.timestamp)
            let last = activityDate(message.lastActivityAt)
            if message.runID != nil && message.runFinishedAt == nil {
                if let last, let stamp, last > stamp { end = max(end ?? last, last) }
            } else {
                for date in [stamp, last].compactMap({ $0 }) { end = max(end ?? date, date) }
            }
        }
        if let end, end >= start {
            for index in indices { result[index] = Int(end.timeIntervalSince(start)) }
        }
    }
    for (index, message) in messages.enumerated() {
        if ["system_triggered", "trigger"].contains(message.role) || (message.role == "user" && (!message.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !message.files.isEmpty)) {
            finish(); boundary = index; indices = []
        } else { indices.append(index) }
    }
    finish()
    return result
}

public func activityDuration(_ seconds: Int) -> String {
    seconds < 60 ? "\(seconds)s" : seconds % 60 == 0 ? "\(seconds / 60)m" : "\(seconds / 60)m \(seconds % 60)s"
}

public func activityFailed(_ part: MessagePart) -> Bool {
    if ["error", "denied", "rejected"].contains(part.state ?? "") || !(part.outcome ?? "").isEmpty { return true }
    guard let data = part.output?.data(using: .utf8), let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
    return object["success"] as? Bool == false || (object["error"] as? String)?.isEmpty == false
}

public func activityKind(_ part: MessagePart) -> String {
    if part.type == "reasoning" { return "reasoning" }
    let name = canonicalActivityTool(part.toolName ?? "")
    if name.contains("command") || name.contains("shell") { return "terminal" }
    if name.contains("search") || name.contains("fetch") { return "search" }
    if name.contains("write") || name.contains("edit") { return "edit" }
    if name.contains("read") { return "read" }
    if name.contains("agent") || name.contains("dispatch") { return "agent" }
    return "tool"
}

public func activityDetail(_ raw: String?, output: Bool = false) -> String {
    guard let raw, let data = raw.data(using: .utf8), let value = try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed]) else { return raw ?? "" }
    if output, let object = value as? [String: Any] {
        if object["success"] as? Bool == false, let error = object["error"] as? String { return error }
        if let message = object["message"] as? String, !message.isEmpty { return message }
    }
    if let string = value as? String { return string }
    guard JSONSerialization.isValidJSONObject(value), let pretty = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]), let text = String(data: pretty, encoding: .utf8) else { return raw }
    return text
}

public func activityFinalStart(_ parts: [MessagePart]) -> Int {
    var start = parts.count
    while start > 0 && parts[start - 1].type == "text" { start -= 1 }
    return start
}

public func activityRows(_ parts: [MessagePart]) -> [MessagePart] {
    var rows: [MessagePart] = []
    for part in normalizeParts(parts) {
        if part.type == "reasoning", rows.last?.type == "reasoning" {
            var merged = part
            merged.text = [rows.last?.text, part.text].compactMap { $0 }.joined(separator: "\n\n")
            rows[rows.count - 1] = merged
        } else { rows.append(part) }
    }
    return rows
}
