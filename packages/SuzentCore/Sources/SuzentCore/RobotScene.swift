/*
 * LICENSE EXCEPTION
 * Use of this file (Robot Character Design and Animation Choreography) is governed by the terms in LICENSE-ASSETS.
 * It is NOT covered by the project's standard Apache 2.0 license.
 */
import Foundation

/// Desktop's RobotAvatar variants (RobotAvatar.tsx), named the same.
public enum RobotVariant: String, CaseIterable, Sendable { case idle, observer, jumper, snoozer, peeker, shaker, skeptic, love, party, eater, dj, workout, portal, scanner }

/// Fixed robot colours, plus `ink` for the floating marks that must read on the card in either theme.
public enum RobotRole: Sendable { case body, eye, ink, gray, dark }

public struct RobotPoint: Equatable, Sendable {
    public let x: Double, y: Double
    public init(_ x: Double, _ y: Double) { self.x = x; self.y = y }
}

/// A 2D affine transform: x' = a·x + c·y + e, y' = b·x + d·y + f.
public struct Affine: Equatable, Sendable {
    public var a = 1.0, b = 0.0, c = 0.0, d = 1.0, e = 0.0, f = 0.0

    public static func * (l: Affine, r: Affine) -> Affine {
        Affine(a: l.a * r.a + l.c * r.b, b: l.b * r.a + l.d * r.b, c: l.a * r.c + l.c * r.d, d: l.b * r.c + l.d * r.d,
               e: l.a * r.e + l.c * r.f + l.e, f: l.b * r.e + l.d * r.f + l.f)
    }
    public func apply(_ p: RobotPoint) -> RobotPoint { RobotPoint(a * p.x + c * p.y + e, b * p.x + d * p.y + f) }

    public static let identity = Affine()
    public static func translate(_ x: Double, _ y: Double) -> Affine { Affine(e: x, f: y) }
    public static func scale(_ x: Double, _ y: Double? = nil) -> Affine { Affine(a: x, d: y ?? x) }
    public static func rotate(_ degrees: Double) -> Affine {
        let r = degrees * .pi / 180
        return Affine(a: cos(r), b: sin(r), c: -sin(r), d: cos(r))
    }
    /// A CSS transform applied around transform-origin (`x`, `y`).
    public static func about(_ x: Double, _ y: Double, _ transform: Affine) -> Affine { translate(x, y) * transform * translate(-x, -y) }
}

public enum RobotMark: Sendable {
    case shape(points: [RobotPoint], role: RobotRole, alpha: Double, stroke: Double)
    /// Text at (`x`, `y`) baseline in robot units, drawn through `matrix` into the slot.
    case glyph(text: String, x: Double, y: Double, size: Double, matrix: Affine, role: RobotRole, alpha: Double)
}

/// Desktop's robot (RobotAvatar.tsx with robot-animations.css) as flat marks in a 32-unit slot. The desktop
/// badge draws the 24-unit robot at 0.75 scale in a 32px box, so one robot unit is one slot unit, offset by 4.
public enum RobotScene {
    public static let slot = 32.0
    private static let toSlot = Affine.translate(4, 4)

    /// Peeker hides below its slot, so its marks are clipped to it.
    public static func clips(_ variant: RobotVariant) -> Bool { variant == .peeker }

    public static func frame(_ variant: RobotVariant, seconds: Double, reduced: Bool = false) -> [RobotMark] {
        let t = reduced ? 0 : seconds
        var marks: [RobotMark] = []
        func rect(_ x: Double, _ y: Double, _ w: Double, _ h: Double, _ r: Double, _ m: Affine, _ role: RobotRole, alpha: Double = 1) {
            marks.append(.shape(points: roundedRect(x, y, w, h, r).map { (toSlot * m).apply($0) }, role: role, alpha: alpha, stroke: 0))
        }
        func ellipse(_ cx: Double, _ cy: Double, _ rx: Double, _ ry: Double, _ m: Affine, _ role: RobotRole, alpha: Double = 1) {
            marks.append(.shape(points: ellipsePoints(cx, cy, rx, ry).map { (toSlot * m).apply($0) }, role: role, alpha: alpha, stroke: 0))
        }
        func path(_ points: [RobotPoint], _ m: Affine, _ role: RobotRole, stroke: Double = 0) {
            marks.append(.shape(points: points.map { (toSlot * m).apply($0) }, role: role, alpha: 1, stroke: stroke))
        }
        func glyph(_ text: String, _ x: Double, _ y: Double, _ size: Double, _ m: Affine, _ role: RobotRole, alpha: Double = 1) {
            marks.append(.glyph(text: text, x: x, y: y, size: size, matrix: toSlot * m, role: role, alpha: alpha))
        }
        func body(_ m: Affine) { rect(0, 0, 24, 24, 4, m, .body) }
        func eyes(_ m: Affine, left: Affine = .identity, right: Affine = .identity) {
            rect(5, 8, 5, 5, 1.5, m * left, .eye)
            rect(14, 8, 5, 5, 1.5, m * right, .eye)
        }
        func face(_ m: Affine, eyes look: Affine = .identity) { body(m); eyes(m, left: look, right: look) }
        func track(_ duration: Double, _ stops: [Double], _ values: [Double], _ curve: Curve = .ease, delay: Double = 0, alternate: Bool = false) -> Double {
            keyframe(cycle(t, duration, delay: delay, alternate: alternate), stops, values, curve)
        }
        let center = (12.0, 12.0), bottom = (12.0, 28.0)
        func about(_ origin: (Double, Double), _ m: Affine) -> Affine { .about(origin.0, origin.1, m) }

        switch variant {
        case .idle:
            let squeeze = track(6.5, [0, 0.94, 0.96, 0.98, 1], [1, 1, 0.25, 1, 1], Curve(0.4, 0, 0.2, 1))
            body(.identity)
            rect(5, 8, 5, 5, 1.5, .about(7.5, 10.5, .scale(1, squeeze)), .eye)
            rect(14, 8, 5, 5, 1.5, .about(16.5, 10.5, .scale(1, squeeze)), .eye)
        case .observer:
            let stops = [0, 0.1, 0.2, 0.25, 0.4, 0.5, 0.6, 0.75, 0.8, 1]
            let x = track(4, stops, [0, -2, -2, 2, 2, 0, 0, 0, 0, 0], .stepEnd)
            let y = track(4, stops, [0, 0, 0, 0, 0, -2, 0, 0, 0, 0], .stepEnd)
            let squeeze = track(4, stops, [1, 1, 1, 1, 1, 1, 1, 0.1, 1, 1], .stepEnd)
            body(.identity)
            eyes(.translate(x, y) * about(center, .scale(1, squeeze)))
        case .jumper:
            let stops = [0, 0.1, 0.45, 0.55, 0.9, 1.0]
            let curves = [Curve.easeOut, .easeOut, Curve(0.2, 0, 0.4, 1), .easeIn, .easeOut]
            let p = cycle(t, 1.2)
            let y = keyframe(p, stops, [0, 0, -6, -6, 0, 0], curves: curves)
            let sx = keyframe(p, stops, [1.15, 0.9, 1, 1, 0.9, 1.15], curves: curves)
            let sy = keyframe(p, stops, [0.85, 1.1, 1, 1, 1.1, 0.85], curves: curves)
            face(.about(12, 24, .translate(0, y) * .scale(sx, sy)))
        case .snoozer:
            let breathe = about(center, .scale(track(4, [0, 0.5, 1], [1, 1.02, 1], .easeInOut)))
            face(breathe, eyes: about(center, .scale(1, track(4, [0, 0.5, 1], [0.1, 0.15, 0.1], .easeInOut))))
            for (index, z) in [("Z", 26.0, 4.0, 5.0), ("z", 28, 8, 4), (".", 27, 12, 3)].enumerated() {
                let p = cycle(t, 3, delay: Double(index))
                let float = Affine.translate(0, keyframe(p, [0, 1], [0, -7.2], .linear)) * .rotate(keyframe(p, [0, 1], [-10, 10], .linear))
                glyph(z.0, z.1, z.2, z.3, breathe * float, .ink, alpha: keyframe(p, [0, 0.2, 0.8, 1], [0, 1, 1, 0], .linear))
            }
        case .peeker:
            let stops = [0, 0.1, 0.2, 0.4, 0.6, 0.7, 0.8, 1]
            let y = track(3, stops, [35.2, 0, 0, 0, 0, 12.8, 0, 35.2], .easeInOut)
            let turn = track(3, stops, [0, 0, -10, 10, 0, 0, 0, 0], .easeInOut)
            let look = track(3, [0, 0.1, 0.2, 0.4, 0.6, 1], [0, 0, -3, 3, 0, 0], .easeInOut)
            face(about(bottom, .translate(0, y) * .rotate(turn)), eyes: .translate(look, 0))
        case .shaker:
            let stops = (0...10).map { Double($0) / 10 }
            let shake = about(center, .translate(track(0.2, stops, [0.5, -0.5, -1.5, 1.5, 0.5, -0.5, -1.5, 1.5, -0.5, 0.5, 0.5]),
                                                 track(0.2, stops, [0.5, -1, 0, 1, -0.5, 1, 0.5, 0.5, -0.5, 1, -1]))
                                  * .rotate(track(0.2, stops, [0, -1, 0, 1, 0, -1, 0, 1, 0, -1, 0])))
            face(shake, eyes: about(center, .scale(track(2, [0, 1], [1, 1.3], alternate: true))))
            for drop in [(-5.0, 2.0, 1.5, 2.0, 0.8, 0.0), (-6, 5, 1, 1.5, 0.7, 0.2), (29, 2, 1.5, 2, 0.8, 0.4), (30, 5, 1, 1.5, 0.7, 0.1)] {
                let p = cycle(t, drop.4, delay: drop.5)
                let fall = Affine.translate(0, keyframe(p, [0, 1], [0, 15])) * .about(drop.0, drop.1, .scale(keyframe(p, [0, 1], [1, 0.5])))
                ellipse(drop.0, drop.1, drop.2, drop.3, shake * fall, .ink, alpha: keyframe(p, [0, 1], [1, 0]))
            }
        case .skeptic:
            let half = [0, 0.5, 1.0]
            let tilt = about(bottom, .rotate(track(3, half, [0, -5, 0], .easeInOut)) * .translate(track(3, half, [0, -2, 0], .easeInOut), 0))
            body(tilt)
            eyes(tilt, left: about(center, .scale(1, track(3, half, [1, 0.6, 1], .easeInOut))),
                 right: .translate(0, track(3, half, [0, -2, 0], .easeInOut)))
            let q = Affine.translate(0, track(3, half, [0, -1, 0], .easeInOut)) * .scale(track(3, half, [1, 1.2, 1], .easeInOut))
            glyph("?", 22, 4, 8, tilt * q, .ink, alpha: track(3, half, [0, 1, 0], .easeInOut))
        case .love:
            let beat = about(center, .scale(track(1, [0, 0.15, 0.3, 0.45, 0.6, 1], [1, 1.1, 1, 1.1, 1, 1])))
            body(beat)
            let pulse = about(center, .scale(track(1, [0, 1], [1, 1.3], alternate: true)))
            glyph("♥", 5.5, 12, 5, beat * pulse, .eye)
            glyph("♥", 14.5, 12, 5, beat * pulse, .eye)
            for heart in [(-4.0, 4.0, 4.0, 0.0), (-2, 0, 3, 0.5), (26, 6, 4, 1), (24, -2, 3, 1.5)] {
                let p = cycle(t, 2, delay: heart.3)
                glyph("♥", heart.0, heart.1, heart.2, beat * .translate(0, keyframe(p, [0, 1], [10, -30], .linear)), .ink,
                      alpha: keyframe(p, [0, 0.2, 0.8, 1], [0, 1, 1, 0], .linear))
            }
        case .party:
            body(.identity)
            let bounce = Affine.translate(0, track(0.5, [0, 0.5, 1], [0, -2, 0], .easeInOut))
            rect(4, 8, 16, 6, 1, bounce, .eye)
            rect(5, 9, 14, 1, 0, bounce, .eye, alpha: 0.5)
        case .eater:
            let stops = [0, 0.1, 0.4, 0.55, 0.65, 0.9, 1]
            let top = Affine.about(4, 15, .translate(0, track(1.5, stops, [0, 0, 0, 1, 0, 0, 0], .easeInOut)) * .rotate(track(1.5, stops, [0, -30, 0, 0, 0, 0, 0], .easeInOut)))
            let jaw = Affine.about(4, 15, .translate(0, track(1.5, stops, [0, 0, 0, -1, 0, 0, 0], .easeInOut)) * .rotate(track(1.5, stops, [0, 30, 0, 0, 0, 0, 0], .easeInOut)))
            path(quadPath([(0, 4)], [((0, 0), (4, 0), false), ((20, 0), (20, 0), true), ((24, 0), (24, 4), false), ((24, 15), (24, 15), true), ((0, 15), (0, 15), true)]), top, .body)
            rect(7.5, 8, 5, 5, 1.5, top, .eye)
            rect(15.5, 8, 5, 5, 1.5, top, .eye)
            path(quadPath([(0, 15)], [((24, 15), (24, 15), true), ((24, 20), (24, 20), true), ((24, 24), (20, 24), false), ((4, 24), (4, 24), true), ((0, 24), (0, 20), false)]), jaw, .body)
            let bites: [[(String, Double)]] = [[("0", 0), ("0", 5), ("0", 10)], [("0", 6)], [("0", 3), ("1", 8)], [("0", 3), ("0", 8)],
                                               [("0", 0), ("0", 5), ("0", 10)], [("1", 6)], [("0", 0), ("1", 5), ("1", 10)], [("0", 6)]]
            for (index, bite) in bites.enumerated() {
                let p = cycle(t, 12, delay: Double(index) * 1.5)
                let alpha = keyframe(p, [0, 0.02, 0.05, 0.051, 1], [0, 1, 1, 0, 0], .linear)
                guard alpha > 0 else { continue }
                let feed = Affine.translate(0, 15) * .translate(keyframe(p, [0, 0.05, 1], [50, 0, 0], .linear), 0) * .scale(keyframe(p, [0, 0.05, 0.051, 1], [0.8, 0.8, 0, 0], .linear))
                for (digit, x) in bite { glyph(digit, x, 2, 6, feed, .ink, alpha: alpha) }
            }
        case .dj:
            let p = cycle(t, 0.5, alternate: true)
            let bop = about(center, .translate(0, keyframe(p, [0, 1], [0, 5], .easeInOut)) * .rotate(keyframe(p, [0, 1], [-2, 2], .easeInOut)))
            path(quadPath([(-2, 12), (-2, 8)], [((-2, -4), (12, -4), false), ((26, -4), (26, 8), false), ((26, 12), (26, 12), true)]), bop, .dark, stroke: 3)
            rect(-5, 8, 5, 10, 2, bop, .dark)
            rect(24, 8, 5, 10, 2, bop, .dark)
            face(bop)
        case .workout:
            let half = [0, 0.5, 1.0]
            let squat = about(bottom, .scale(1, track(1.8, half, [0.9, 1, 0.9], .easeInOut)))
            let lift = squat * .translate(0, track(1.8, half, [4, -8, 4], .easeInOut))
            rect(-3, 5, 2, 7, 0.5, lift * .about(-2, 5, .rotate(track(1.8, half, [-15, 0, -15], .easeInOut))), .gray)
            rect(25, 5, 2, 7, 0.5, lift * .about(26, 5, .rotate(track(1.8, half, [15, 0, 15], .easeInOut))), .gray)
            rect(-6, 5, 36, 1.5, 0.75, lift, .body)
            rect(-8, 0, 3, 10, 0, lift, .body)
            rect(29, 0, 3, 10, 0, lift, .body)
            body(squat)
            rect(5.5, 9, 5, 2, 0, squat, .eye)
            rect(13.5, 9, 5, 2, 0, squat, .eye)
            ellipse(23, 10, 0.8, 1.5, squat * .translate(0, track(1.8, half, [0, 0, 10])), .gray, alpha: track(1.8, half, [0, 1, 0]))
        case .portal:
            ellipse(12, -4, 12, 3, .about(12, -6, .scale(track(2, [0, 0.2, 0.4, 1], [0.8, 1.1, 0.8, 0.8], .easeInOut))), .body)
            let stops = [0, 0.2, 0.5, 0.8, 1.0]
            let alpha = track(2, stops, [0, 1, 1, 0, 0], .easeInOut)
            if alpha > 0 {
                let teleport = about(center, .translate(0, track(2, stops, [-20, 0, 0, 20, 22], .easeInOut)) * .scale(track(2, stops, [0, 0.6, 0.6, 0, 0], .easeInOut))
                                     * .rotate(track(2, stops, [-90, 0, 0, 90, 0], .easeInOut)))
                rect(0, 0, 24, 24, 4, teleport, .body, alpha: alpha)
                rect(5, 8, 5, 5, 1.5, teleport, .eye, alpha: alpha)
                rect(14, 8, 5, 5, 1.5, teleport, .eye, alpha: alpha)
            }
            ellipse(12, 28, 12, 3, .about(12, 30, .scale(track(2, [0, 0.6, 0.8, 1], [0.8, 0.8, 1.1, 0.8], .easeInOut))), .body)
        case .scanner:
            // The 90% box shrinks the robot to .9 of a slot unit, then it leans back under 150px perspective.
            func tilt(_ point: RobotPoint) -> RobotPoint {
                let x = (point.x - 12) * 0.9, y = (point.y - 12) * 0.9
                let k = 150 / (150 - y * sin(.pi / 4))
                return RobotPoint(16 + x * k, 16 + y * cos(.pi / 4) * k)
            }
            for (x, y, w, h, r, role) in [(0.0, 0.0, 24.0, 24.0, 4.0, RobotRole.body), (5, 8, 5, 5, 1.5, .eye), (14, 8, 5, 5, 1.5, .eye)] {
                marks.append(.shape(points: roundedRect(x, y, w, h, r).map(tilt), role: role, alpha: 1, stroke: 0))
            }
            let p = cycle(t, 2)
            let sweep = keyframe(p, [0, 0.1, 0.9, 1], [0, 1, 1, 0], .linear)
            let left = keyframe(p, [0, 1], [-slot, slot], .linear)
            let strips = 8.0
            for index in 0..<Int(strips) {
                let x = left + Double(index) * slot / strips
                let glow = 0.5 * (1 - abs((Double(index) + 0.5) / strips * 2 - 1))
                marks.append(.shape(points: [RobotPoint(x, 0), RobotPoint(x + slot / strips, 0), RobotPoint(x + slot / strips, slot), RobotPoint(x, slot)],
                                    role: .eye, alpha: glow * sweep, stroke: 0))
            }
        }
        return marks
    }

    private static func roundedRect(_ x: Double, _ y: Double, _ w: Double, _ h: Double, _ r: Double) -> [RobotPoint] {
        guard r > 0 else { return [RobotPoint(x, y), RobotPoint(x + w, y), RobotPoint(x + w, y + h), RobotPoint(x, y + h)] }
        let corners = [(x + w - r, y + r, -90.0), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)]
        return corners.flatMap { cx, cy, start in
            (0...4).map { step in
                let angle = (start + Double(step) * 22.5) * .pi / 180
                return RobotPoint(cx + r * cos(angle), cy + r * sin(angle))
            }
        }
    }

    private static func ellipsePoints(_ cx: Double, _ cy: Double, _ rx: Double, _ ry: Double) -> [RobotPoint] {
        (0..<24).map { step in
            let angle = Double.pi * 2 * Double(step) / 24
            return RobotPoint(cx + rx * cos(angle), cy + ry * sin(angle))
        }
    }

    /// SVG M/L/Q segments flattened; each segment is (control, end, straight).
    private static func quadPath(_ start: [(Double, Double)], _ segments: [((Double, Double), (Double, Double), Bool)]) -> [RobotPoint] {
        var points = start.map { RobotPoint($0.0, $0.1) }
        for (control, end, straight) in segments {
            let from = points[points.count - 1]
            if straight { points.append(RobotPoint(end.0, end.1)); continue }
            for step in 1...8 {
                let u = Double(step) / 8
                points.append(RobotPoint((1 - u) * (1 - u) * from.x + 2 * u * (1 - u) * control.0 + u * u * end.0,
                                         (1 - u) * (1 - u) * from.y + 2 * u * (1 - u) * control.1 + u * u * end.1))
            }
        }
        return points
    }
}
