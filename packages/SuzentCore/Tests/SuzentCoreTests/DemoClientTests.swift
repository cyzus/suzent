import Foundation
import Testing
@testable import SuzentCore

@MainActor private final class DemoEvents: Sendable {
    var buffer = LiveActivityBuffer()
    func receive(_ event: StreamEvent) { buffer.consume(event) }
}

@Test @MainActor func demoStreamsAndPersistsWithoutAConnection() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let storage = directory.appendingPathComponent("demo.json")
    let client = try DemoClient(storageURL: storage, language: "en", streamDuration: 0.01)
    let chat = try await client.createChat(title: "Test", projectID: "demo-travel")
    let events = DemoEvents()
    try await client.send("Plan a trip", chatID: chat.id, model: nil, attachments: [])
    try await client.observe(chat.id) { await events.receive($0) }
    let saved = try await client.chat(chat.id)
    #expect(saved.isRunning == false)
    #expect(saved.messages?.count == 2)
    #expect(saved.messages?.last?.content.contains("London") == true)
    #expect(events.buffer.drain()?.contains { $0.type == "text" } == true)
    let restored = try DemoClient(storageURL: storage, language: "en")
    #expect(try await restored.chat(chat.id).messages?.last?.content == saved.messages?.last?.content)
}

@Test @MainActor func demoApprovalAllowsRejectsAndStops() async throws {
    let client = try DemoClient(language: "en", streamDuration: 0.01)
    let chat = try await client.createChat(title: "Tools")
    for allowed in [true, false] {
        try await client.send("tool approval", chatID: chat.id, model: nil, attachments: [])
        let state = try await client.approvals(chat.id)
        let request = try #require(state.pending.first)
        #expect(request.actions.first?.behavior == "allow")
        try await client.decideApprovals(chat.id, pending: state.pending, choices: [request.id: allowed ? "allow" : "reject"])
        try await client.observe(chat.id) { _ in }
        let saved = try await client.chat(chat.id)
        #expect(saved.messages?.last?.content.contains(allowed ? "Approved" : "rejected") == true)
        #expect(try await client.approvals(chat.id).pending.isEmpty)
    }
    try await client.send("tool", chatID: chat.id, model: nil, attachments: [])
    try await client.stop(chat.id)
    #expect(try await client.chat(chat.id).messages?.last?.content.contains("stopped") == true)
    #expect(try await client.approvals(chat.id).pending.isEmpty)
}

@Test @MainActor func demoManagementReplayAndResetStayLocal() async throws {
    let client = try DemoClient(language: "en", streamDuration: 0.01)
    let chat = try await client.createChat(title: "Original")
    try await client.manageChat(chat.id, action: "pin")
    try await client.manageChat(chat.id, action: "rename", value: "Renamed")
    try await client.manageChat(chat.id, action: "move", value: "demo-travel")
    let managed = try await client.chat(chat.id)
    #expect(managed.title == "Renamed" && managed.pinned == true && managed.projectId == "demo-travel")
    try await client.send("hello", chatID: chat.id, model: nil, attachments: [])
    try await client.observe(chat.id) { _ in }
    let fork = try await client.messageAction(chat.id, index: 1, action: "fork")
    #expect(try await client.chat(fork).messages?.count == 2)
    _ = try await client.messageAction(chat.id, index: 0, action: "edit", text: "trip")
    try await client.observe(chat.id) { _ in }
    #expect(try await client.chat(chat.id).messages?.first?.content == "trip")
    _ = try await client.messageAction(chat.id, index: 1, action: "retry")
    try await client.observe(chat.id) { _ in }
    #expect(try await client.chat(chat.id).messages?.count == 2)
    try await client.manageChat(chat.id, action: "delete")
    #expect(try await !client.chats().contains { $0.id == chat.id })
    try client.reset()
    #expect(try await client.chats().count == 7)
}

@Test @MainActor func demoAttachmentsUseOnlyMetadataAndAreScoped() async throws {
    let client = try DemoClient(language: "en", streamDuration: 0.01)
    let chat = try await client.createChat(title: "Attachments")
    // A nonexistent path proves that demo upload neither opens nor transmits file bytes.
    let attachment = PendingAttachment(url: URL(fileURLWithPath: "/nonexistent/demo-photo.png"), name: "photo.png", mimeType: "image/png")
    let ids = try await client.upload([attachment], chatID: chat.id)
    do {
        try await client.send("", chatID: "demo-welcome", model: nil, attachments: ids)
        Issue.record("Cross-chat upload accepted")
    } catch ClientError.http(400) {}
    try await client.send("", chatID: chat.id, model: nil, attachments: ids)
    try await client.observe(chat.id) { _ in }
    let saved = try await client.chat(chat.id)
    #expect(saved.messages?.first?.files.first?.filename == "photo.png")
    #expect(saved.messages?.last?.content.contains("nothing is uploaded") == true)
}

@Test @MainActor func demoObserverDetachesWithoutResendingAndRecovers() async throws {
    let client = try DemoClient(language: "en", streamDuration: 0.08)
    let chat = try await client.createChat(title: "Background")
    try await client.send("hello", chatID: chat.id, model: nil, attachments: [])
    let observer = Task { try await client.observe(chat.id) { _ in } }
    try await Task.sleep(for: .milliseconds(10))
    observer.cancel()
    _ = await observer.result
    let composer = try await client.composer()
    #expect(composer.id.isEmpty)
    let independent = try await client.createChat(title: "Independent")
    try await client.send("New work", chatID: independent.id, model: nil, attachments: [])
    try await client.observe(independent.id) { _ in }
    #expect(try await client.chat(independent.id).messages?.first?.content == "New work")
    try await Task.sleep(for: .milliseconds(100))
    let saved = try await client.chat(chat.id)
    #expect(saved.isRunning == false && saved.messages?.count == 2)
    #expect(try await client.approvals(chat.id).pending.isEmpty)
}

@Test @MainActor func demoReopenMarksUnfinishedTurnsAndUsesChineseSamples() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let storage = directory.appendingPathComponent("demo.json")
    let client = try DemoClient(storageURL: storage, language: "zh-Hans")
    #expect(client.prompts.first?.contains("旅行") == true)
    let chat = try await client.createChat(title: "测试")
    try await client.send("工具审批", chatID: chat.id, model: nil, attachments: [])
    let restored = try DemoClient(storageURL: storage, language: "zh-Hans")
    #expect(try await restored.chat(chat.id).isRunning == false)
    #expect(try await restored.chat(chat.id).messages?.last?.content.contains("中断") == true)
    try restored.reset()
    #expect(try await restored.chats().count == 7)
}

@Test @MainActor func demoRetryAfterApprovalRequestsAFreshDecision() async throws {
    let client = try DemoClient(language: "en", streamDuration: 0.01)
    let chat = try await client.createChat(title: "Approval retry")
    try await client.send("tool", chatID: chat.id, model: nil, attachments: [])
    var previous = ""
    for (index, decision) in ["allow", "reject", "allow"].enumerated() {
        let state = try await client.approvals(chat.id)
        let request = try #require(state.pending.first)
        #expect(request.id != previous)
        previous = request.id
        try await client.decideApprovals(chat.id, pending: state.pending, choices: [request.id: decision])
        try await client.observe(chat.id) { _ in }
        #expect(try await client.chat(chat.id).isRunning == false)
        #expect(try await client.approvals(chat.id).pending.isEmpty)
        if index < 2 { _ = try await client.messageAction(chat.id, index: 1, action: "retry") }
    }
}

@Test @MainActor func demoExamplesIncludeSuccessfulAndFailedActivities() async throws {
    for language in ["en", "zh"] {
        let client = try DemoClient(language: language)
        let success = try await client.chat("demo-ui")
        let failure = try await client.chat("demo-failure")
        #expect(success.messages?.last?.parts.filter { $0.type == "tool" }.count == 2)
        #expect(failure.messages?.last?.parts.contains(where: activityFailed) == true)
        #expect(try await client.chat("demo-note").messages?.last?.content.isEmpty == false)
    }
}
