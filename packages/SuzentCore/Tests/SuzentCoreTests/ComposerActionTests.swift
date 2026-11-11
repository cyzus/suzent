import Foundation
import Testing
@testable import SuzentCore

@Test func composerKeepsStopAndHangUpReachable() {
    #expect(ComposerAction.resolve(hasContent: false, busy: false, running: false, voiceActive: false, voiceConnecting: false) == .voice)
    #expect(ComposerAction.resolve(hasContent: true, busy: false, running: false, voiceActive: false, voiceConnecting: false) == .send)
    #expect(ComposerAction.resolve(hasContent: false, busy: false, running: false, voiceActive: true, voiceConnecting: false) == .hangUp)
    #expect(ComposerAction.resolve(hasContent: false, busy: false, running: false, voiceActive: true, voiceConnecting: true) == .connecting)
    #expect(ComposerAction.resolve(hasContent: true, busy: true, running: true, voiceActive: true, voiceConnecting: true) == .connecting)
    #expect(ComposerAction.resolve(hasContent: true, busy: true, running: false, voiceActive: false, voiceConnecting: false) == .loading)
}

@Test func mobileVoiceAnimationIsBundledOffline() {
    #expect(VoiceAnimation.html.contains("updateVoiceCube"))
    #expect(VoiceAnimation.html.contains("webgl2"))
    #expect(VoiceAnimation.html.contains("default-src 'none'"))
    #expect(!VoiceAnimation.html.contains("<script src="))
}

@Test func activeCallKeepsOnlyHangUpWhileTaskRuns() {
    for busy in [false, true] {
        for content in [false, true] {
            #expect(ComposerAction.resolve(hasContent: content, busy: busy, running: true, voiceActive: true, voiceConnecting: false) == .hangUp)
        }
        #expect(ComposerAction.resolve(hasContent: false, busy: busy, running: true, voiceActive: false, voiceConnecting: false) == .stop)
    }
}

@Test func typingDuringATurnRedirectsOrQueuesInsteadOfStopping() {
    #expect(ComposerAction.resolve(hasContent: true, busy: false, running: true, voiceActive: false, voiceConnecting: false, canRedirect: true) == .redirect)
    #expect(ComposerAction.resolve(hasContent: true, busy: false, running: true, voiceActive: false, voiceConnecting: false, canRedirect: false) == .queue)
    #expect(ComposerAction.resolve(hasContent: true, busy: true, running: true, voiceActive: false, voiceConnecting: false, canRedirect: true) == .loading)
    #expect(ComposerAction.resolve(hasContent: false, busy: false, running: true, voiceActive: false, voiceConnecting: false, canRedirect: true) == .stop)
}

@Test func queuesAreKeptPerConversationInOrder() {
    let first = QueuedMessage(text: "first")
    let second = QueuedMessage(text: "second", attachments: [PendingAttachment(url: URL(fileURLWithPath: "/tmp/a.png"), name: "a.png", mimeType: "image/png")])
    var queues = MessageQueues()
    queues.add(first, to: "a"); queues.add(second, to: "a"); queues.add(QueuedMessage(text: "other"), to: "b")
    #expect(queues.of("a") == [first, second])
    #expect(queues.attachments.map(\.name) == ["a.png"])
    queues.remove(first.id, from: "a")
    #expect(queues.of("a") == [second])
    queues.clear("a")
    #expect(queues.of("a").isEmpty)
    #expect(queues.of("b").count == 1)
    #expect(queues.of(nil).isEmpty)
}

@Test func redirectKeepsThePartialReplyAndEndsUnfinishedTools() {
    #expect(interruptedReply([], model: "m") == nil)
    let reply = interruptedReply([
        MessagePart(type: "reasoning", text: "thinking", state: "running"),
        MessagePart(type: "tool", toolName: "bash", toolCallId: "t1", state: "running"),
        MessagePart(type: "tool", toolName: "write", toolCallId: "t2", state: "approval-requested"),
        MessagePart(type: "tool", toolName: "read", toolCallId: "t3", state: "completed"),
        MessagePart(type: "text", text: "Halfway"),
    ], model: "m")
    #expect(reply?.role == "assistant")
    #expect(reply?.content == "Halfway")
    #expect(reply?.model == "m")
    #expect(reply?.parts.map(\.state) == ["completed", "error", "error", "completed", nil])
}
