import Foundation

/// A CSS timing function, so keyframes ported from the desktop stylesheet ease the same way.
public struct Curve: Sendable {
    public let x1, y1, x2, y2: Double
    public var stepEnd = false

    public init(_ x1: Double, _ y1: Double, _ x2: Double, _ y2: Double, stepEnd: Bool = false) {
        (self.x1, self.y1, self.x2, self.y2, self.stepEnd) = (x1, y1, x2, y2, stepEnd)
    }

    public func at(_ t: Double) -> Double {
        if stepEnd { return t >= 1 ? 1 : 0 }
        if t <= 0 { return 0 }
        if t >= 1 { return 1 }
        func bezier(_ u: Double, _ a: Double, _ b: Double) -> Double { 3 * a * u * (1 - u) * (1 - u) + 3 * b * u * u * (1 - u) + u * u * u }
        var low = 0.0, high = 1.0
        for _ in 0..<24 {
            let mid = (low + high) / 2
            if bezier(mid, x1, x2) < t { low = mid } else { high = mid }
        }
        return bezier((low + high) / 2, y1, y2)
    }

    public static let linear = Curve(0, 0, 1, 1)
    public static let ease = Curve(0.25, 0.1, 0.25, 1)
    public static let easeIn = Curve(0.42, 0, 1, 1)
    public static let easeOut = Curve(0, 0, 0.58, 1)
    public static let easeInOut = Curve(0.42, 0, 0.58, 1)
    public static let stepEnd = Curve(0, 0, 1, 1, stepEnd: true)
}

/// Where an infinite CSS animation is in its cycle, 0...1; `alternate` plays every other cycle backwards.
public func cycle(_ seconds: Double, _ duration: Double, delay: Double = 0, alternate: Bool = false) -> Double {
    let elapsed = (seconds - delay) / duration
    let progress = elapsed - elapsed.rounded(.down)
    return alternate && Int(elapsed.rounded(.down)) % 2 != 0 ? 1 - progress : progress
}

/// One property's CSS keyframes; `curves` overrides the timing function per segment, like animation-timing-function inside a keyframe.
public func keyframe(_ progress: Double, _ stops: [Double], _ values: [Double], _ curve: Curve = .ease, curves: [Curve]? = nil) -> Double {
    if progress <= stops[0] { return values[0] }
    for index in 1..<stops.count where progress <= stops[index] {
        let span = stops[index] - stops[index - 1]
        let local = span <= 0 ? 1 : (progress - stops[index - 1]) / span
        return values[index - 1] + (values[index] - values[index - 1]) * (curves?[index - 1] ?? curve).at(local)
    }
    return values[values.count - 1]
}

/// A running tool icon's offset (desktop px on its 14px icon), turn, scale and fade, plus the scan sweep line.
public struct ToolIconPose: Sendable, Equatable {
    public var dx = 0.0, dy = 0.0, rotation = 0.0, scale = 1.0, alpha = 1.0, sweepY = 0.0, sweepAlpha = 0.0

    public init() {}
}

/// Desktop's tool-icon-* keyframes (styles.css) for each `activityToolAnimation` kind.
public func toolIconPose(_ kind: String, seconds: Double) -> ToolIconPose {
    func track(_ duration: Double, _ curve: Curve, _ stops: [Double], _ values: [Double]) -> Double {
        keyframe(cycle(seconds, duration), stops, values, curve)
    }
    let sharp = Curve(0.4, 0, 0.2, 1)
    var pose = ToolIconPose()
    switch kind {
    case "pending":
        pose.rotation = track(1.4, sharp, [0, 0.3, 0.7, 1], [0, 12, -12, 0])
    case "terminal":
        pose.alpha = track(1, .easeInOut, [0, 0.5, 1], [1, 0.35, 1])
        pose.scale = track(1, .easeInOut, [0, 0.5, 1], [1, 0.95, 1])
    case "scan":
        pose.sweepY = track(1.25, sharp, [0, 1], [-7, 7])
        pose.sweepAlpha = track(1.25, sharp, [0, 0.2, 0.8, 1], [0, 0.85, 0.85, 0])
    case "typewriter":
        let strike = Curve(0.36, 0.07, 0.19, 0.97), stops = [0, 0.35, 0.7, 1.0]
        pose.dx = track(0.75, strike, stops, [0, 0.75, -0.5, 0])
        pose.dy = track(0.75, strike, stops, [0, -1, 0.25, 0])
        pose.rotation = track(0.75, strike, stops, [0, -8, 3, 0])
    case "radar":
        let stops = [0, 0.33, 0.66, 1.0]
        pose.dx = track(1.3, .easeInOut, stops, [0, -0.75, 0.75, 0])
        pose.dy = track(1.3, .easeInOut, stops, [0, -0.5, 0.5, 0])
        pose.scale = track(1.3, .easeInOut, stops, [1, 1.1, 0.96, 1])
    case "signal":
        pose.scale = track(1, .easeInOut, [0, 0.5, 1], [1, 1.14, 1])
        pose.alpha = track(1, .easeInOut, [0, 0.5, 1], [1, 0.65, 1])
    case "memory":
        pose.alpha = track(1.2, .easeInOut, [0, 0.4, 0.75, 1], [1, 0.45, 0.85, 1])
        pose.scale = track(1.2, .easeInOut, [0, 0.4, 0.75, 1], [1, 0.93, 1.04, 1])
    case "snap":
        pose.dy = track(1, Curve(0.34, 1.56, 0.64, 1), [0, 0.3, 0.6, 1], [0, -1.25, 1, 0])
    case "cursor":
        let stops = [0, 0.4, 0.65, 1.0]
        pose.dx = track(1.15, sharp, stops, [0, 1, 1, 0])
        pose.dy = track(1.15, sharp, stops, [0, -1, -1, 0])
        pose.scale = track(1.15, sharp, stops, [1, 1.04, 0.88, 1])
    default: break
    }
    return pose
}

/// One frame of desktop's brutal-running-* surface: where the wave's peak is (fraction of twice the width) and how far the grid has slid (px).
public struct RunningSurfaceFrame: Sendable, Equatable {
    public let wave: Double, gridShift: Double, stops: [Double], alphas: [Double]
}

/// Desktop's brutal-running-{mono,dots,scan} backgrounds, with the lighter inline alphas activity-turn-tool uses.
public func runningSurfaceFrame(_ kind: String, seconds: Double) -> RunningSurfaceFrame {
    let duration = kind == "scan" ? 1.2 : kind == "dots" ? 1.4 : 1.35
    let u = cycle(seconds, duration)
    switch kind {
    case "scan": return RunningSurfaceFrame(wave: u, gridShift: 0, stops: [0, 0.42, 0.48, 0.5, 0.52, 0.58, 1], alphas: [0, 0, 0.09, 0.28, 0.09, 0, 0])
    case "dots": return RunningSurfaceFrame(wave: u, gridShift: 12 * u, stops: [0, 0.35, 0.5, 0.65, 1], alphas: [0, 0.06, 0.13, 0.06, 0])
    default: return RunningSurfaceFrame(wave: u, gridShift: 12 * u, stops: [0, 0.35, 0.5, 0.65, 1], alphas: [0, 0.05, 0.12, 0.05, 0])
    }
}

/// One frame of desktop's reasoning-thinking-label: the sweep image's background-position and the ink bar's span, both as fractions of the word.
public struct ThinkingLabelFrame: Sendable, Equatable {
    public let sweep: Double, barStart: Double, barEnd: Double
}

/// Desktop's reasoning-thinking-sweep and -redact (1.8s): the bar wipes on in six steps, holds, wipes off, then the
/// sweep's pale notch, parked off the right edge until then, runs back over the word.
public func thinkingLabelFrame(seconds: Double) -> ThinkingLabelFrame {
    let u = cycle(seconds, 1.8)
    let sweep = u < 0.6 ? 0.2 : 0.8 - (u - 0.6) / 0.4 * 0.6
    if u < 0.24 { return ThinkingLabelFrame(sweep: sweep, barStart: 0, barEnd: (u / 0.24 * 6).rounded(.down) / 6) }
    if u < 0.36 { return ThinkingLabelFrame(sweep: sweep, barStart: 0, barEnd: 1) }
    if u < 0.56 { return ThinkingLabelFrame(sweep: sweep, barStart: ((u - 0.36) / 0.2 * 6).rounded(.down) / 6, barEnd: 1) }
    return ThinkingLabelFrame(sweep: sweep, barStart: 1, barEnd: 1)
}
