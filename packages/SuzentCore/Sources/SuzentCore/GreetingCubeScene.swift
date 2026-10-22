import Foundation

public struct GreetingPoint: Sendable {
    public let x: Double
    public let y: Double
}

public struct GreetingMark: Sendable {
    public let points: [GreetingPoint]
    public let color: UInt32
    public var alpha: Double = 1
    public var stroke: Bool = false
    public var width: Double = 0.65
}

/// The empty-chat "greeting" cube, ported from the desktop web UI's
/// `GreetingCube`. Draws a floating 3-D cube (front face = Suzent logo eyes),
/// a slowly rotating sigil behind it, and a soft shadow, on a 160x160 canvas.
///
/// `frame` is a pure, deterministic function of time so the Kotlin and Swift
/// ports stay equivalent and unit-testable.
public enum GreetingCubeScene {
    private static let cx = 80.0
    private static let cubeHalf = 34.0
    private static let cubeCy = 64.0
    private static let sigilCy = 76.0
    private static let shadowCy = 118.0

    private static let faceFront: UInt32 = 0x000000
    private static let faceBack: UInt32 = 0x050505
    private static let faceRight: UInt32 = 0x181818
    private static let faceLeft: UInt32 = 0x070707
    private static let faceTop: UInt32 = 0x303030
    private static let faceBottom: UInt32 = 0x030303
    private static let eye: UInt32 = 0xFFFFFF
    private static let edge: UInt32 = 0xFFFFFF

    public static func frame(seconds: Double, engaged: Bool, reduced: Bool, inkColor: UInt32) -> [GreetingMark] {
        let t = reduced ? 0 : max(0, seconds)
        var marks: [GreetingMark] = []

        let floatY = reduced ? 0 : -1.5 + 3.5 * cos(2 * Double.pi * t / 5.4)
        let baseX = engaged ? 27.0 : 22.0
        let turnX = reduced ? 0 : 4.0 * sin(2 * Double.pi * t / 8.0)
        let turnY = reduced ? 0 : 4.0 + 10.0 * (0.5 + 0.5 * sin(2 * Double.pi * t / 8.0 + 1.2))
        let turnZ = reduced ? 0 : sin(2 * Double.pi * t / 4.0)
        let rotX = (baseX + turnX) * Double.pi / 180
        let rotY = (-30.0 - turnY) * Double.pi / 180
        let rotZ = turnZ * Double.pi / 180

        let squint = (engaged || reduced) ? 1.0 : 0.08
        let sigilAlpha = engaged ? 0.5 : 0.1

        addSigil(&marks, t: t, reduced: reduced, color: inkColor, alpha: sigilAlpha)
        addShadow(&marks, t: t, reduced: reduced, color: inkColor)
        addCube(&marks, rotX: rotX, rotY: rotY, rotZ: rotZ, cy: cubeCy + floatY, squint: squint)
        return marks
    }

    private static func rotate(_ x: Double, _ y: Double, _ z: Double, _ rx: Double, _ ry: Double, _ rz: Double) -> (Double, Double, Double) {
        let cy = cos(ry); let sy = sin(ry)
        let x1 = x * cy + z * sy
        let z1 = -x * sy + z * cy
        let cx = cos(rx); let sx = sin(rx)
        let y2 = y * cx - z1 * sx
        let z2 = y * sx + z1 * cx
        let cz = cos(rz); let sz = sin(rz)
        return (x1 * cz - y2 * sz, x1 * sz + y2 * cz, z2)
    }

    private static func project(_ x: Double, _ y: Double, _ cy: Double) -> GreetingPoint {
        GreetingPoint(x: cx + x, y: cy - y)
    }

    private static func frontProject(_ u: Double, _ v: Double, _ rx: Double, _ ry: Double, _ rz: Double, _ cy: Double) -> GreetingPoint {
        let q = rotate(u, v, cubeHalf, rx, ry, rz)
        return project(q.0, q.1, cy)
    }

    private static func roundRect(_ cx: Double, _ cy: Double, _ w: Double, _ h: Double, _ r: Double) -> [(Double, Double)] {
        let left = cx - w / 2; let top = cy - h / 2; let right = cx + w / 2; let bottom = cy + h / 2
        let rad = min(r, min(w / 2, h / 2))
        var pts: [(Double, Double)] = []
        func corner(_ cx0: Double, _ cy0: Double, _ a0: Double, _ a1: Double) {
            for i in 0..<4 {
                let a = a0 + (a1 - a0) * Double(i) / 4
                pts.append((cx0 + rad * cos(a), cy0 + rad * sin(a)))
            }
        }
        pts.append((left + rad, top))
        pts.append((right - rad, top))
        corner(right - rad, top + rad, -Double.pi / 2, 0)
        pts.append((right, bottom - rad))
        corner(right - rad, bottom - rad, 0, Double.pi / 2)
        pts.append((left + rad, bottom))
        corner(left + rad, bottom - rad, Double.pi / 2, Double.pi)
        pts.append((left, top + rad))
        corner(left + rad, top + rad, Double.pi, 3 * Double.pi / 2)
        return pts
    }

    private static func ellipse(_ cx: Double, _ cy: Double, _ rx: Double, _ ry: Double, steps: Int = 24) -> [(Double, Double)] {
        (0..<steps).map { i in
            let a = 2 * Double.pi * Double(i) / Double(steps)
            return (cx + rx * cos(a), cy + ry * sin(a))
        }
    }

    private static func scaleP(_ pts: [(Double, Double)], _ sx: Double, _ sy: Double, _ px: Double, _ py: Double) -> [(Double, Double)] {
        pts.map { (px + ($0.0 - px) * sx, py + ($0.1 - py) * sy) }
    }

    private static func rotate2(_ pts: [(Double, Double)], _ angle: Double) -> [(Double, Double)] {
        let c = cos(angle); let s = sin(angle)
        return pts.map { ($0.0 * c - $0.1 * s, $0.0 * s + $0.1 * c) }
    }

    private static func addCube(_ marks: inout [GreetingMark], rotX: Double, rotY: Double, rotZ: Double, cy: Double, squint: Double) {
        let h = cubeHalf
        let verts: [(Double, Double, Double)] = [
            (-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h),
            (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h),
        ].map { rotate($0.0, $0.1, $0.2, rotX, rotY, rotZ) }

        func face(_ indices: [Int], _ color: UInt32, _ nx: Double, _ ny: Double, _ nz: Double) {
            let n = rotate(nx, ny, nz, rotX, rotY, rotZ)
            if n.2 <= 0 { return }
            let pts = indices.map { project(verts[$0].0, verts[$0].1, cy) }
            marks.append(GreetingMark(points: pts, color: color))
            marks.append(GreetingMark(points: pts, color: edge, alpha: 0.3, stroke: true, width: 0.8))
        }
        face([4, 5, 6, 7], faceFront, 0, 0, 1)
        face([1, 0, 3, 2], faceBack, 0, 0, -1)
        face([1, 5, 6, 2], faceRight, 1, 0, 0)
        face([0, 4, 7, 3], faceLeft, -1, 0, 0)
        face([3, 2, 6, 7], faceTop, 0, 1, 0)
        face([0, 1, 5, 4], faceBottom, 0, -1, 0)

        func drawEye(_ sign: Double) {
            let ex = sign * 0.375 * h
            let ey = 0.125 * h
            var pts = roundRect(ex, ey, 0.4167 * h, 0.4167 * h, 0.125 * h)
            if squint != 1 { pts = scaleP(pts, 1, squint, ex, ey) }
            marks.append(GreetingMark(points: pts.map { frontProject($0.0, $0.1, rotX, rotY, rotZ, cy) }, color: eye))
        }
        drawEye(-1)
        drawEye(1)
    }

    private static func addSigil(_ marks: inout [GreetingMark], t: Double, reduced: Bool, color: UInt32, alpha: Double) {
        let outer = reduced ? 0 : 2 * Double.pi * (t / 32.0)
        let inner = reduced ? 0 : -2 * Double.pi * (t / 24.0)
        let nodePulse = reduced ? 0.5 : 0.28 + 0.44 * (0.5 + 0.5 * sin(2 * Double.pi * t / 4.0))

        func shape(_ points: [(Double, Double)], _ angle: Double, _ width: Double) {
            let pts = rotate2(points, angle).map { GreetingPoint(x: cx + $0.0, y: sigilCy + $0.1) }
            marks.append(GreetingMark(points: pts, color: color, alpha: alpha, stroke: true, width: width))
        }

        let diamond: [(Double, Double)] = [(0, -70), (70, 0), (0, 70), (-70, 0)]
        let square: [(Double, Double)] = [(-50, -50), (50, -50), (50, 50), (-50, 50)]
        shape(diamond, outer, 0.8)
        shape(square, outer, 0.8)
        for tick in [[(0.0, -70.0), (0.0, -58.0)], [(70.0, 0.0), (58.0, 0.0)], [(0.0, 70.0), (0.0, 58.0)], [(-70.0, 0.0), (-58.0, 0.0)]] {
            shape(tick, outer, 0.8)
        }

        shape([(0, -48), (42, 26), (-42, 26)], inner, 0.7)
        shape([(0, 48), (-42, -26), (42, -26)], inner, 0.7)

        addDashedLine(&marks, color: color, alpha: alpha, x1: 0, y1: -60, x2: 0, y2: 60)
        addDashedLine(&marks, color: color, alpha: alpha, x1: -60, y1: 0, x2: 60, y2: 0)

        for pos in [(0.0, -72.5), (72.5, 0.0), (0.0, 72.5), (-72.5, 0.0)] {
            let pts = roundRect(cx + pos.0, sigilCy + pos.1, 5, 5, 1).map { GreetingPoint(x: $0.0, y: $0.1) }
            marks.append(GreetingMark(points: pts, color: color, alpha: alpha * nodePulse))
        }
    }

    private static func addDashedLine(_ marks: inout [GreetingMark], color: UInt32, alpha: Double, x1: Double, y1: Double, x2: Double, y2: Double) {
        let dx = x2 - x1; let dy = y2 - y1
        let len = (dx * dx + dy * dy).squareRoot()
        let ux = dx / len; let uy = dy / len
        let dash = 4.0; let gap = 14.0
        var pos = 0.0
        while pos < len {
            let end = min(pos + dash, len)
            marks.append(GreetingMark(
                points: [GreetingPoint(x: cx + x1 + ux * pos, y: sigilCy + y1 + uy * pos), GreetingPoint(x: cx + x1 + ux * end, y: sigilCy + y1 + uy * end)],
                color: color, alpha: alpha, stroke: true, width: 0.7))
            pos += dash + gap
        }
    }

    private static func addShadow(_ marks: inout [GreetingMark], t: Double, reduced: Bool, color: UInt32) {
        let a = reduced ? 0.11 : 0.11 + 0.03 * sin(2 * Double.pi * t / 5.4)
        let sx = reduced ? 1.0 : 0.89 + 0.11 * cos(2 * Double.pi * t / 5.4)
        let rx = 31.0 * sx
        marks.append(GreetingMark(points: ellipse(cx, shadowCy, rx, 3.5).map { GreetingPoint(x: $0.0, y: $0.1) }, color: color, alpha: a * 0.6))
        marks.append(GreetingMark(points: ellipse(cx, shadowCy, rx * 0.8, 2.8).map { GreetingPoint(x: $0.0, y: $0.1) }, color: color, alpha: a * 0.8))
    }
}
