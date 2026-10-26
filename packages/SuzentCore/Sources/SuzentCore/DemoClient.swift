import Foundation

/// An isolated, persistent sample workspace. This client has no network transport or credentials.
@MainActor public final class DemoClient: MobileClient {
    private struct Run {
        let id = UUID().uuidString
        var text: String
        var started = Date()
        var pending: Bool
        var decision: Bool?
        var visible = 0
        let tool: Bool
    }

    private let strings: [String: Any]
    private let storageURL: URL?
    private let streamDuration: TimeInterval
    private var records: [[String: Any]]
    private var runs: [String: Run] = [:]
    private var uploads: [String: (chat: String, file: [String: String])] = [:]

    public var prompts: [String] { [label("prompt"), label("tool_prompt")] }

    public init(storageURL: URL? = nil, language: String = Locale.preferredLanguages.first ?? "en",
                streamDuration: TimeInterval = 4) throws {
        let data = try Data(contentsOf: Bundle.module.url(forResource: "demo", withExtension: "json")!)
        let fixture = try JSONSerialization.jsonObject(with: data) as! [String: [String: Any]]
        strings = fixture[language.lowercased().hasPrefix("zh") ? "zh" : "en"]!
        self.storageURL = storageURL
        self.streamDuration = max(0.001, streamDuration)
        records = strings["chats"] as! [[String: Any]]
        if let storageURL, FileManager.default.fileExists(atPath: storageURL.path) {
            let saved = try JSONSerialization.jsonObject(with: Data(contentsOf: storageURL)) as? [String: Any]
            guard saved?["version"] as? Int == 1, let chats = saved?["chats"] as? [[String: Any]] else {
                throw ClientError.invalidResponse
            }
            // Validate persisted data before exposing it to the regular conversation UI.
            _ = try decode([Chat].self, chats)
            records = chats
            for index in records.indices where records[index]["isRunning"] as? Bool == true {
                var messages = records[index]["messages"] as? [[String: Any]] ?? []
                messages.append(message("assistant", label("interrupted"), model: records[index]["model"] as? String))
                records[index]["messages"] = messages
                records[index]["isRunning"] = false
            }
        }
    }

    public nonisolated func close() {}

    public func reset() throws {
        runs = [:]; uploads = [:]
        records = strings["chats"] as! [[String: Any]]
        try save()
    }

    public func clientSession() async throws -> ClientSession {
        let permissions = ClientPermissions(chatIds: [], allChats: true, createChats: true, manageChats: true,
                                            send: true, stop: true, approveTools: true)
        return ClientSession(device: ClientDevice(deviceId: "offline-demo", displayName: "Suzent Demo", platform: "demo", permissions: permissions),
                             clientProtocol: 1, streamProtocols: [1], pairingRepair: nil, attachments: 1, scheduledTasks: 1)
    }

    public func projects() async throws -> [Project] { try decode([Project].self, strings["projects"]!) }
    public func scheduledTasks() async throws -> [ScheduledTask] { try decode([ScheduledTask].self, strings["tasks"]!) }

    public func chats() async throws -> [Chat] {
        for id in Array(runs.keys) { try advance(id) }
        return try decode([Chat].self, records.map { item in
            var summary = item; summary["messages"] = []; return summary
        })
    }

    public func composer() async throws -> Chat {
        try decode(Chat.self, ["id": "", "title": "", "messages": [], "projectId": "demo-home",
                              "projectName": label("home"), "model": label("model"),
                              "models": [label("model"), label("alternate_model")]])
    }

    public func createChat(title: String, projectID: String? = nil) async throws -> Chat {
        let project = (try await projects()).first { $0.id == (projectID ?? "demo-home") }
        guard let project else { throw ClientError.http(400) }
        let item: [String: Any] = ["id": UUID().uuidString, "title": title, "messages": [], "isRunning": false,
                                  "projectId": project.id, "projectName": project.name, "model": label("model"),
                                  "models": [label("model"), label("alternate_model")]]
        records.insert(item, at: 0); try save()
        return try decode(Chat.self, item)
    }

    public func chat(_ id: String) async throws -> Chat {
        try advance(id)
        return try decode(Chat.self, records[try index(id)])
    }

    public func manageChat(_ id: String, action: String, value: String? = nil) async throws {
        try advance(id)
        let i = try index(id)
        guard runs[id] == nil else { throw ClientError.http(409) }
        switch action {
        case "pin", "unpin": records[i]["pinned"] = action == "pin"
        case "rename":
            guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw ClientError.http(400) }
            records[i]["title"] = value
        case "move":
            guard let project = (try await projects()).first(where: { $0.id == value }) else { throw ClientError.http(400) }
            records[i]["projectId"] = project.id; records[i]["projectName"] = project.name
        case "delete": records.remove(at: i)
        default: throw ClientError.http(400)
        }
        try save()
    }

    public func upload(_ attachments: [PendingAttachment], chatID: String) async throws -> [String] {
        _ = try index(chatID)
        guard attachments.count <= 10 else { throw ClientError.http(400) }
        return attachments.map { item in
            let id = UUID().uuidString
            uploads[id] = (chatID, ["filename": item.name, "mime_type": item.mimeType])
            return id
        }
    }

    public func send(_ text: String, chatID: String, model: String? = nil, attachments: [String] = []) async throws {
        try advance(chatID)
        let i = try index(chatID)
        guard runs[chatID] == nil else { throw ClientError.http(409) }
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !attachments.isEmpty else { throw ClientError.http(400) }
        guard attachments.allSatisfy({ uploads[$0]?.chat == chatID }) else { throw ClientError.http(400) }
        if let model {
            guard (records[i]["models"] as? [String] ?? []).contains(model) else { throw ClientError.http(400) }
            records[i]["model"] = model
        }
        var messages = records[i]["messages"] as? [[String: Any]] ?? []
        var user = message("user", text)
        user["files"] = attachments.compactMap { uploads[$0]?.file }
        messages.append(user)
        records[i]["messages"] = messages
        if messages.count == 1, !text.isEmpty { records[i]["title"] = String(text.prefix(60)) }
        let tool = matches(text, key: "keywords_tool")
        let reply = !attachments.isEmpty ? label("attachment") : matches(text, key: "keywords_trip") ? label("plan") : label("generic")
        runs[chatID] = Run(text: reply, pending: tool, tool: tool)
        records[i]["isRunning"] = true
        for id in attachments { uploads.removeValue(forKey: id) }
        let record = records.remove(at: i); records.insert(record, at: 0)
        try save()
    }

    public func approvals(_ id: String) async throws -> ApprovalState {
        _ = try index(id); try advance(id)
        let run = runs[id]
        let pending = run?.pending == true ? [approval(run!)] : []
        return ApprovalState(pending: pending, isRunning: run != nil)
    }

    public func decideApprovals(_ id: String, pending: [ApprovalRequest], choices: [String: String]) async throws {
        guard var run = runs[id], run.pending,
              pending.map(\.id) == [run.id], let action = choices[run.id], ["allow", "reject"].contains(action) else {
            throw ClientError.http(409)
        }
        run.pending = false; run.decision = action == "allow"
        run.text = label(action == "allow" ? "allowed" : "denied"); run.started = Date()
        runs[id] = run
    }

    public func stop(_ chatID: String) async throws {
        _ = try index(chatID)
        guard var run = runs[chatID] else { return }
        run.text = String(run.text.prefix(run.visible)) + label("stopped")
        runs[chatID] = run
        try finish(chatID)
    }

    public func messageAction(_ id: String, index messageIndex: Int, action: String, text: String? = nil, model: String? = nil) async throws -> String {
        try advance(id)
        let i = try index(id)
        guard runs[id] == nil else { throw ClientError.http(409) }
        var messages = records[i]["messages"] as? [[String: Any]] ?? []
        guard messages.indices.contains(messageIndex) else { throw ClientError.http(400) }
        if action == "fork" {
            let target = try await createChat(title: "\(records[i]["title"] as? String ?? "") · \(label("branch"))", projectID: records[i]["projectId"] as? String)
            records[try index(target.id)]["messages"] = Array(messages.prefix(messageIndex + 1))
            try save(); return target.id
        }
        guard ["edit", "retry"].contains(action), let user = messages.lastIndex(where: { $0["role"] as? String == "user" }) else { throw ClientError.http(400) }
        let original = messages[user]
        let outgoing = action == "edit" ? (text ?? "") : original["content"] as? String ?? ""
        var issued: [String] = []
        for file in original["files"] as? [[String: String]] ?? [] {
            let token = UUID().uuidString; uploads[token] = (id, file); issued.append(token)
        }
        messages = Array(messages.prefix(user))
        records[i]["messages"] = messages
        try await send(outgoing, chatID: id, model: model, attachments: issued)
        return id
    }

    public func observe(_ chatID: String, onEvent: @Sendable (StreamEvent) async -> Void) async throws {
        var emitted = 0
        var decision: Bool?
        guard let initial = runs[chatID] else { return }
        try await emit(["type": "STREAM_RESET"], to: onEvent)
        try await emit(["type": "THINKING_TEXT_MESSAGE_CONTENT", "delta": label("reasoning")], to: onEvent)
        try await emit(["type": "THINKING_END"], to: onEvent)
        if initial.tool {
            try await emit(["type": "CUSTOM", "name": "tool_approval_request", "value": ["toolCallId": initial.id,
                "toolName": "demo.create_note", "args": "{\"path\":\"weekend-plan.md\"}"]], to: onEvent)
        }
        while let run = runs[chatID], run.id == initial.id {
            try Task.checkCancellation()
            if run.pending { try await Task.sleep(for: .milliseconds(80)); continue }
            if run.tool, run.decision != decision {
                decision = run.decision
                try await emit(["type": "CUSTOM", "name": "tool_approval_result", "value": ["toolCallId": run.id,
                    "status": run.decision == true ? "executed" : "rejected", "output": label(run.decision == true ? "allowed" : "denied")]], to: onEvent)
            }
            let count = min(run.text.count, Int(Date().timeIntervalSince(run.started) / streamDuration * Double(run.text.count)))
            if count > emitted {
                try await emit(["type": "TEXT_MESSAGE_CONTENT", "messageId": run.id,
                                "delta": String(run.text.dropFirst(emitted).prefix(count - emitted))], to: onEvent)
                emitted = count
                runs[chatID]?.visible = count
            }
            if count >= run.text.count { try finish(chatID); break }
            try await Task.sleep(for: .milliseconds(60))
        }
    }

    private func advance(_ id: String) throws {
        if let run = runs[id], !run.pending, Date().timeIntervalSince(run.started) >= streamDuration { try finish(id) }
    }

    private func finish(_ id: String) throws {
        guard let run = runs.removeValue(forKey: id) else { return }
        let i = try index(id)
        var parts: [[String: Any]] = [["type": "reasoning", "text": label("reasoning"), "state": "completed"]]
        if run.tool {
            parts.append(["type": "tool", "toolCallId": run.id, "toolName": "demo.create_note",
                          "args": "{\"path\":\"weekend-plan.md\"}", "output": run.decision == nil ? label("stopped") : label(run.decision == true ? "allowed" : "denied"),
                          "state": run.decision == true ? "completed" : "error"])
        }
        parts.append(["type": "text", "text": run.text, "citationSources": [["id": "demo-source", "type": "web",
                     "title": label("source_title"), "url": "https://suzent.com/docs", "snippet": label("source_snippet")]]])
        var result = message("assistant", run.text, model: records[i]["model"] as? String)
        result["parts"] = parts
        var messages = records[i]["messages"] as? [[String: Any]] ?? []
        messages.append(result); records[i]["messages"] = messages; records[i]["isRunning"] = false
        try save()
    }

    private func approval(_ run: Run) -> ApprovalRequest {
        ApprovalRequest(id: run.id, kind: "tool", toolName: "demo.create_note", args: "{\"path\":\"weekend-plan.md\"}",
                        reason: label("approval_reason"), actions: [ApprovalAction(id: "allow", behavior: "allow"), ApprovalAction(id: "reject", behavior: "deny")])
    }
    private func label(_ key: String) -> String { strings[key] as? String ?? key }
    private func matches(_ text: String, key: String) -> Bool {
        (strings[key] as? [String] ?? []).contains { text.lowercased().contains($0) }
    }
    private func index(_ id: String) throws -> Int {
        guard let i = records.firstIndex(where: { $0["id"] as? String == id }) else { throw ClientError.http(404) }
        return i
    }
    private func message(_ role: String, _ text: String, model: String? = nil) -> [String: Any] {
        var result: [String: Any] = ["role": role, "content": text, "timestamp": ISO8601DateFormatter().string(from: Date())]
        if let model { result["model"] = model }
        return result
    }
    private func decode<T: Decodable>(_ type: T.Type, _ value: Any) throws -> T {
        try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }
    private func save() throws {
        guard let storageURL else { return }
        try FileManager.default.createDirectory(at: storageURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: ["version": 1, "chats": records]).write(to: storageURL, options: .atomic)
    }
    private func emit(_ value: [String: Any], to callback: @Sendable (StreamEvent) async -> Void) async throws {
        await callback(try decode(StreamEvent.self, value))
    }
}
