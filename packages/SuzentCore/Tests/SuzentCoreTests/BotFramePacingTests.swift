import Testing
@testable import SuzentCore

@Test func botPacingFollowsDisplayAndCapsAt120() {
    let pacing = BotFramePacing()
    #expect(pacing.framesPerSecond(displayRate: 60) == 60)
    #expect(pacing.framesPerSecond(displayRate: 90) == 90)
    #expect(pacing.framesPerSecond(displayRate: 144) == 120)
}

@Test func botPacingFallsBackAndRecoversWithoutFlapping() {
    var pacing = BotFramePacing()
    for _ in 0..<7 { pacing.record(workSeconds: 0.008, displayRate: 120) }
    #expect(!pacing.limited)
    pacing.record(workSeconds: 0.008, displayRate: 120)
    #expect(pacing.limited)
    #expect(pacing.framesPerSecond(displayRate: 120) == 60)
    for _ in 0..<239 { pacing.record(workSeconds: 0.002, displayRate: 120) }
    #expect(pacing.limited)
    pacing.record(workSeconds: 0.002, displayRate: 120)
    #expect(!pacing.limited)
}
