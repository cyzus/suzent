import Foundation
import Testing
@testable import SuzentCore

@Test func nativePresentationContract() throws {
    struct Fixture: Decodable {
        let name: String
        let messages: [ChatMessage]
        let texts: [String]
        let activities: [Int]
    }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/presentation-fixtures.json"))
    for fixture in try JSONDecoder().decode([Fixture].self, from: data) {
        let rows = presentMessages(fixture.messages)
        #expect(rows.map(\.text) == fixture.texts, "\(fixture.name)")
        #expect(rows.map { $0.parts.filter { $0.type != "text" }.count } == fixture.activities, "\(fixture.name)")
    }
}

@Test func sharedActivityReplayContract() throws {
    struct Fixture: Decodable {
        let name: String
        let events: [StreamEvent]
        let types: [String]
        let chunks: [Int]
        let args: [String]
        let outputs: [String]
        let texts: [String]
        let states: [String]
    }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/activity-fixtures.json"))
    for fixture in try JSONDecoder().decode([Fixture].self, from: data) {
        var buffer = LiveActivityBuffer()
        for event in fixture.events { buffer.consume(event) }
        let snapshot = buffer.drain()
        let parts = try #require(snapshot)
        #expect(parts.map(\.type) == fixture.types, "\(fixture.name)")
        #expect(parts.map { $0.args ?? "" } == fixture.args)
        #expect(parts.map { $0.output ?? "" } == fixture.outputs)
        #expect(parts.map { $0.text ?? "" } == fixture.texts)
        #expect(parts.map { $0.state ?? "" } == fixture.states)
        #expect(activityChunks(parts).map(\.count) == fixture.chunks)
        let next = buffer.drain()
        #expect(next == nil)
    }
}

@Test func batchesDeltasAndFlushesFinalChunk() {
    var buffer = LiveActivityBuffer()
    for _ in 0..<100 { buffer.consume(StreamEvent(type: "TEXT_MESSAGE_CONTENT", delta: "a", message: nil)) }
    let batch = buffer.drain()
    #expect(batch?.first?.text == String(repeating: "a", count: 100))
    let idle = buffer.drain()
    #expect(idle == nil)
    buffer.consume(StreamEvent(type: "TEXT_MESSAGE_CONTENT", delta: "尾", message: nil))
    let final = buffer.drain()
    #expect(final?.first?.text == String(repeating: "a", count: 100) + "尾")
    buffer.consume(StreamEvent(type: "STREAM_RESET", delta: nil, message: nil))
    let reset = buffer.drain()
    #expect(reset == [])
}

@Test func resolvesCitationSourcesStoredInAnotherMessage() throws {
    let data = Data(#"[{"role":"assistant","parts":[{"type":"text","text":"Weather \uE200cite\uE202t0_src_1\uE201"}]},{"role":"assistant","parts":[{"type":"citation-sources","citationSources":[{"id":"t0_src_1","type":"webpage","title":"Forecast","url":"https://example.com/weather"}]}]}]"#.utf8)
    let messages = try JSONDecoder().decode([ChatMessage].self, from: data)
    let row = try #require(presentMessages(messages).first)

    #expect(markdownWithCitationLinks(row.text, sources: row.citationSources) == "Weather [Forecast](<https://example.com/weather>)")
}

@Test func footerKeepsPerMessageMetadataAndOriginalIndex() throws {
    let data = Data(#"{"id":"test","title":"Test","messages":[{"role":"user","content":"Question","timestamp":"2026-09-30T12:00:00Z"},{"role":"assistant","content":"Answer","model":"provider/old-model","timestamp":"2026-09-30T12:01:00Z"}]}"#.utf8)
    let chat = try JSONDecoder().decode(Chat.self, from: data)
    let rows = presentMessages(chat.messages ?? [])
    #expect(rows[0].timestamp == "2026-09-30T12:00:00Z")
    #expect(rows[1].model == "provider/old-model")
    #expect(rows[1].timestamp == "2026-09-30T12:01:00Z")
    #expect(rows[1].messageIndex == 1)
}

@Test func activityAndFinalAnswerShareOneMessageWithFinalMetadata() throws {
    let data = Data(#"[{"role":"user","content":"Question"},{"role":"assistant","parts":[{"type":"reasoning","text":"Thinking"}]},{"role":"assistant","parts":[{"type":"text","text":"Checking"},{"type":"tool","toolName":"read_file","toolCallId":"one","output":"ok"}]},{"role":"assistant","content":"Answer","model":"provider/model","timestamp":"2026-09-30T12:01:00Z"},{"role":"system_triggered","content":"Scheduled task"},{"role":"assistant","content":"Next answer"}]"#.utf8)
    let messages = try JSONDecoder().decode([ChatMessage].self, from: data)
    let rows = presentMessages(messages)
    #expect(rows.map(\.role) == ["user", "assistant", "system_triggered", "assistant"])
    let answer = rows[1]
    #expect(answer.parts.map(\.type) == ["reasoning", "text", "tool", "text"])
    #expect(answer.text == "Checking\n\nAnswer")
    #expect(activityChunks(answer.parts).map(\.count) == [1, 1, 1, 1])
    #expect(answer.model == "provider/model")
    #expect(answer.timestamp == "2026-09-30T12:01:00Z")
    #expect(answer.messageIndex == 3)
}

@Test func systemRemindersFollowDesktopPresentation() throws {
    struct Fixture: Decodable {
        let name: String
        let content: String
        let title: String?
        let body: String?
        let collapsed: Bool?
    }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/system-reminder-fixtures.json"))
    for fixture in try JSONDecoder().decode([Fixture].self, from: data) {
        let reminder = SystemReminder(fixture.content)
        #expect(reminder?.title == fixture.title, "\(fixture.name)")
        #expect(reminder?.body == fixture.body, "\(fixture.name)")
        #expect(reminder?.initiallyCollapsed == fixture.collapsed, "\(fixture.name)")
    }
}

@Test func hiddenReminderPreservesTurnBoundary() throws {
    let data = Data(#"[{"role":"assistant","parts":[{"type":"reasoning","text":"Thinking"}]},{"role":"system_triggered","content":"<!-- suzent-agent-inbox:hidden -->"},{"role":"assistant","content":"New turn"}]"#.utf8)
    let rows = presentMessages(try JSONDecoder().decode([ChatMessage].self, from: data))
    #expect(rows.count == 2)
    #expect(rows.map(\.messageIndex) == [0, 2])
    #expect(rows[1].text == "New turn")
}

@Test func reminderMetadataIsRemovedWithoutChangingUserMessages() throws {
    let data = Data(#"[{"role":"user","content":"<!-- suzent-agent-inbox:literal -->"},{"role":"system_triggered","parts":[{"type":"text","text":"<!-- suzent-agent-inbox:private -->\n**Agent done**\nResult"}]}]"#.utf8)
    let rows = presentMessages(try JSONDecoder().decode([ChatMessage].self, from: data))
    #expect(rows.map(\.role) == ["user", "system_triggered"])
    #expect(rows[0].text == "<!-- suzent-agent-inbox:literal -->")
    #expect(rows[1].text == "**Agent done**\nResult")
}

@Test func backgroundActivityBatchesKeepEveryDeltaAndReset() async {
    let accumulator = LiveActivityAccumulator()
    let producer = Task {
        for _ in 0..<2_000 {
            await accumulator.consume(StreamEvent(type: "TEXT_MESSAGE_CONTENT", delta: "块😀", message: nil))
        }
    }
    var latest = ""
    for _ in 0..<500 {
        if let parts = await accumulator.drain() {
            let text = parts.first?.text ?? ""
            #expect(text.hasPrefix(latest))
            latest = text
        }
        await Task.yield()
    }
    await producer.value
    if let parts = await accumulator.drain() { latest = parts.first?.text ?? "" }
    #expect(latest == String(repeating: "块😀", count: 2_000))
    await accumulator.consume(StreamEvent(type: "STREAM_RESET", delta: nil, message: nil))
    await accumulator.consume(StreamEvent(type: "TEXT_MESSAGE_CONTENT", delta: "尾", message: nil))
    let reset = await accumulator.drain()
    #expect(reset?.first?.text == "尾")
}

@Test @MainActor func savedPresentationCacheInvalidatesForMessagesAndLiveTools() throws {
    let cache = ChatPresentationCache()
    let source = """
    [{"role":"user","content":"Question"},
     {"role":"tool","name":"read_file","tool_call_id":"one","content":"Result"},
     {"role":"assistant","content":"Answer","model":"model-a","timestamp":"2026-01-01T00:00:00Z"}]
    """
    let messages = try JSONDecoder().decode([ChatMessage].self, from: Data(source.utf8))
    let initial = cache.content(messages)
    #expect(initial.flatMap(\.parts).contains { $0.type == "tool" })
    #expect(cache.content(messages).map(\.text) == initial.map(\.text))
    #expect(!cache.content(messages, liveToolIDs: ["one"]).flatMap(\.parts).contains { $0.type == "tool" })
    #expect(cache.content(messages).flatMap(\.parts).contains { $0.type == "tool" })
    let changed = try JSONDecoder().decode([ChatMessage].self, from: Data(source.replacingOccurrences(of: "model-a", with: "model-b").utf8))
    #expect(cache.content(changed).last?.model == "model-b")
    #expect(cache.content([]).isEmpty)
}

@Test func railSummaryMatchesDesktopCategoriesAndDeduplicatesFiles() {
    let parts = [
        MessagePart(type: "tool", toolName: "Read", args: #"{"file_path":"./src/main.py"}"#),
        MessagePart(type: "tool", toolName: "read_file", args: #"{"path":"src/main.py"}"#),
        MessagePart(type: "tool", toolName: "Edit", args: #"{"path":"src/main.py"}"#),
        MessagePart(type: "tool", toolName: "Bash"),
        MessagePart(type: "tool", toolName: "mcp__server__web_search"),
        MessagePart(type: "tool", toolName: "read_file", state: "running"),
        MessagePart(type: "tool", toolName: "write_file", state: "error")]
    let summary = activitySummary(parts, live: true)
    #expect(summary.map(\.kind) == ["read", "changed", "commands", "searches", "running", "failed"])
    #expect(summary.map(\.count) == [1, 1, 1, 1, 1, 1])
    #expect(activitySummary(parts, live: false)[4].kind == "other")
    let named = [
        MessagePart(type: "tool", toolName: "webpage_fetch"), MessagePart(type: "tool", toolName: "agent_dispatch", args: #"{"agent_id":"new"}"#),
        MessagePart(type: "tool", toolName: "agent_dispatch", args: #"{"agent_id":"a1"}"#), MessagePart(type: "tool", toolName: "update_task"),
        MessagePart(type: "tool", toolName: "memory_update"), MessagePart(type: "tool", toolName: "skill_execute"), MessagePart(type: "tool", toolName: "speak")]
    #expect(activitySummary(named, live: false).map(\.kind) == ["web", "delegated", "agents", "tasks", "memory", "skills", "other"])
    let alone = activitySummary([MessagePart(type: "tool", toolName: "speak"), MessagePart(type: "tool", toolName: "render_ui"),
                                 MessagePart(type: "tool", toolName: "speak", state: "error")], live: false)
    #expect(alone.map(\.kind) == ["failed", "tools"])
    #expect(alone.map(\.count) == [1, 2])
    #expect(canonicalActivityTool("ReadFile") == "read_file")
    #expect(activityToolLabel(parts[0]) == "read file: ./src/main.py")
    #expect(activityToolLabel(MessagePart(type: "tool", toolName: "Read", args: "{")) == "read file")
    let reasoning = [MessagePart(type: "reasoning", text: "One"), MessagePart(type: "text", text: " "), MessagePart(type: "reasoning", text: "Two")]
    #expect(activityChunks(reasoning).count == 1)
    #expect(activityStepCount(activityChunks(reasoning)[0]) == 1)
}
