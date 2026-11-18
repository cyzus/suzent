import Foundation

public struct BotFramePacing: Sendable {
    public private(set) var limited = false
    private var slowFrames = 0
    private var fastFrames = 0

    public init() {}

    public func framesPerSecond(displayRate: Double) -> Double {
        min(max(displayRate, 1), limited ? 60 : 120)
    }

    public mutating func record(workSeconds: Double, displayRate: Double) {
        guard displayRate > 60 else { return }
        let budget = 1 / min(displayRate, 120)
        if !limited {
            slowFrames = workSeconds > budget * 0.8 ? slowFrames + 1 : 0
            if slowFrames >= 8 { limited = true; slowFrames = 0 }
        } else {
            fastFrames = workSeconds < budget * 0.5 ? fastFrames + 1 : 0
            if fastFrames >= 240 { limited = false; fastFrames = 0 }
        }
    }
}
