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
    ["error", "denied", "rejected"].contains(part.state ?? "") || toolCallFailed(part)
}

/// Desktop's toolCallFailed: the tool itself reported failure; a denial is not one.
public func toolCallFailed(_ part: MessagePart) -> Bool {
    if !(part.outcome ?? "").isEmpty { return true }
    guard let data = part.output?.data(using: .utf8), let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
    return object["success"] as? Bool == false || (object["error"] as? String)?.isEmpty == false
}

/// Desktop's AgentBadge BADGE_WEIGHTS: the resting personality, picked once per badge from `roll` in 0...1.
public func robotPersonality(_ roll: Double) -> RobotVariant {
    let weights: [(RobotVariant, Double)] = [(.idle, 20), (.observer, 20), (.peeker, 10), (.jumper, 5), (.party, 5), (.love, 2), (.dj, 2)]
    var left = roll * weights.reduce(0) { $0 + $1.1 }
    for (variant, weight) in weights {
        left -= weight
        if left <= 0 { return variant }
    }
    return .idle
}

/// The tool the badge reacts to: the first still without output, else the turn's last part when it is a tool.
public func robotCurrentTool(_ parts: [MessagePart]) -> String? {
    let tool = parts.first { $0.type == "tool" && ($0.output ?? "").isEmpty } ?? parts.last.flatMap { $0.type == "tool" ? $0 : nil }
    return tool?.toolName
}

/// Desktop's AgentBadge variant: a fresh failure startles it, approval makes it skeptical, each tool has its face.
public func robotBadgeVariant(base: RobotVariant, startled: Bool, pending: Bool, streaming: Bool, tool: String?) -> RobotVariant {
    if startled { return .shaker }
    if pending { return .skeptic }
    if let tool {
        switch canonicalActivityTool(tool) {
        case "read_file", "webpage_fetch": return .eater
        case "glob_search", "grep_search": return .scanner
        case "web_search": return .peeker
        case "run_command", "start_command", "write_file", "edit_file": return .workout
        case "agent": return .portal
        case "skill_execute": return .dj
        default: return .observer
        }
    }
    return streaming ? .observer : base
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

private let exactToolIcons: [String: String] = [
    "read_file": "document-text", "write_file": "document-plus", "edit_file": "pencil-square", "glob_search": "folder-open",
    "grep_search": "magnifying-glass", "run_command": "command-line", "start_command": "play", "check_command": "signal",
    "stop_command": "stop", "web_search": "globe-alt", "webpage_fetch": "arrow-down-on-square", "browser_action": "cursor-arrow-rays",
    "memory_search": "cpu-chip", "memory_update": "cpu-chip", "session_search": "chat-bubble-left-right", "manage_goal": "flag",
    "create_tasks": "clipboard-document-list", "update_task": "clipboard-document-check", "list_tasks": "clipboard-document-list", "schedule_cron": "calendar-days",
    "skill_execute": "bolt", "search_tools": "magnifying-glass", "render_ui": "squares-2x2", "ask_question": "question-mark-circle",
    "generate_image": "photo", "edit_image": "paint-brush", "analyze_image": "eye", "analyze_visual": "eye",
    "generate_video": "film", "check_video_status": "film", "speak": "speaker-wave", "social_message": "paper-airplane",
    "agent": "user-group", "agent_list": "user-group", "agent_read": "user-group", "agent_send": "user-group",
    "agent_dispatch": "user-group", "agent_stop": "user-group",
]

private let fallbackToolIcons: [(keys: [String], icon: String)] = [
    (["agent", "subagent"], "user-group"),
    (["memory"], "cpu-chip"),
    (["session", "chat"], "chat-bubble-left-right"),
    (["browser"], "cursor-arrow-rays"),
    (["fetch", "scrape"], "arrow-down-on-square"),
    (["web"], "globe-alt"),
    (["glob", "dir"], "folder-open"),
    (["search", "grep", "find"], "magnifying-glass"),
    (["edit", "patch", "replace"], "pencil-square"),
    (["write", "create_file"], "document-plus"),
    (["read"], "document-text"),
    (["file", "folder"], "folder"),
    (["bash", "shell", "python", "command", "cmd", "exec"], "command-line"),
    (["database", "sql", "db"], "circle-stack"),
    (["goal"], "flag"),
    (["task", "plan", "todo"], "clipboard-document-list"),
    (["schedule", "cron"], "calendar-days"),
    (["skill"], "bolt"),
    (["image", "photo"], "photo"),
    (["video"], "film"),
    (["speak", "audio", "voice"], "speaker-wave"),
]

/// Desktop's pickToolIcon (toolGroupIcon.tsx): the Heroicon each tool row shows. `approval` is "pending" or "denied".
public func activityToolIcon(_ toolName: String, approval: String? = nil) -> String {
    if approval == "pending" { return "clock" }
    if approval == "denied" { return "no-symbol" }
    let name = canonicalActivityTool(toolName)
    if let icon = exactToolIcons[name] { return icon }
    return fallbackToolIcons.first { $0.keys.contains(where: name.contains) }?.icon ?? "wrench-screwdriver"
}

private let fallbackToolAnimations: [(keys: [String], kind: String)] = [
    (["bash", "shell", "command", "cmd"], "terminal"),
    (["read", "fetch"], "scan"),
    (["write", "edit"], "typewriter"),
    (["search", "grep", "glob"], "radar"),
    (["memory"], "memory"),
    (["browser"], "cursor"),
]

/// Desktop's pickToolAnimationKind: how a running tool's icon moves; "none" once it has output.
public func activityToolAnimation(_ toolName: String, approval: String? = nil, running: Bool = false, hasOutput: Bool = false) -> String {
    if approval == "denied" { return "none" }
    if approval == "pending" { return "pending" }
    if !running || hasOutput { return "none" }
    let name = canonicalActivityTool(toolName)
    switch name {
    case "run_command", "start_command", "stop_command": return "terminal"
    case "check_command", "speak", "social_message": return "signal"
    case "read_file", "webpage_fetch", "analyze_image", "analyze_visual", "agent_read": return "scan"
    case "write_file", "edit_file", "create_tasks", "update_task", "manage_goal", "edit_image", "generate_image", "generate_video", "render_ui": return "typewriter"
    case "glob_search", "grep_search", "web_search", "search_tools", "list_tasks", "agent_list": return "radar"
    case "memory_search", "session_search", "agent", "agent_send", "agent_dispatch": return "memory"
    case "skill_execute", "schedule_cron": return "snap"
    case "browser_action": return "cursor"
    default: return fallbackToolAnimations.first { $0.keys.contains(where: name.contains) }?.kind ?? "terminal"
    }
}
