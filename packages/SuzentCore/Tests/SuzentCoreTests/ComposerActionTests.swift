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
    for content in [false, true] {
        for busy in [false, true] {
            #expect(ComposerAction.resolve(hasContent: content, busy: busy, running: true, voiceActive: true, voiceConnecting: false) == .hangUp)
            #expect(ComposerAction.resolve(hasContent: content, busy: busy, running: true, voiceActive: false, voiceConnecting: false) == .stop)
        }
    }
}
