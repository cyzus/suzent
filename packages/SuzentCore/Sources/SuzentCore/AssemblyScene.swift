import Foundation

public struct AssemblyPoint: Sendable {
    public let x: Double
    public let y: Double
}

public struct AssemblyMark: Sendable {
    public let points: [AssemblyPoint]
    public let color: UInt32
    public var alpha: Double = 1
    public var stroke: Bool = false
    public var width: Double = 0.65
}

public enum AssemblyScene {
    public static let duration = 5.5
    private static func ease(_ value: Double) -> Double {
        let v = min(1, max(0, value))
        return v * v * (3 - 2 * v)
    }
    private static func rotate(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double, Double) {
        let a = x * cos(-0.48) + z * sin(-0.48)
        let b = -x * sin(-0.48) + z * cos(-0.48)
        return (a, y * cos(0.32) - b * sin(0.32), y * sin(0.32) + b * cos(0.32))
    }
    private static func random(_ cycle: Int, _ block: Int, _ salt: Int) -> Double {
        let v = sin(1729 + Double(cycle) * 127.1 + Double(block) * 311.7 + Double(salt) * 74.7) * 43758.5453
        return v - floor(v)
    }
    public static func frame(seconds: Double, reduced: Bool = false) -> [AssemblyMark] {
        let t = reduced ? 3.2 : max(0, seconds) * 1.45
        let cycle = t.truncatingRemainder(dividingBy: duration)
        let cycleID = Int(floor(t / duration))
        var marks: [AssemblyMark] = []
        let advance = ease((cycle - 4.3) / 1.2) * 76
        let shell = ease((cycle - 1.5) / 0.28)
        let awake = ease((cycle - 2.7) / 0.3)
        func project(_ x: Double, _ y: Double, _ z: Double, _ center: Double) -> AssemblyPoint {
            let q = rotate(x, y, z)
            return AssemblyPoint(x: center + q.0, y: 56 - q.1)
        }
        func cube(_ center: Double, _ size: Double, offset: (Double, Double, Double) = (0, 0, 0), alpha: Double = 1, eyes: Double = 0) {
            guard alpha > 0 else { return }
            let coordinates: [(Double, Double, Double)] = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
            let vertices = coordinates.map { project($0.0 * size + offset.0, $0.1 * size + offset.1, $0.2 * size + offset.2, center) }
            let faces: [([Int], UInt32)] = [([3,2,6,7],51),([1,5,6,2],25),([4,7,6,5],9)]
            for (indices, shade) in faces {
                let points = indices.map { vertices[$0] }
                let color = (shade << 16) | ((shade + 1) << 8) | (shade + 2)
                marks.append(AssemblyMark(points: points, color: color, alpha: alpha))
                marks.append(AssemblyMark(points: points, color: 0x454749, alpha: alpha, stroke: true))
            }
            if eyes > 0 {
                for x in [-0.43, 0.43] {
                    let positions = [(x-0.16,0.23-eyes/2),(x+0.16,0.23-eyes/2),(x+0.16,0.23+eyes/2),(x-0.16,0.23+eyes/2)]
                    marks.append(AssemblyMark(points: positions.map { project($0.0 * size,$0.1 * size,1.012 * size,center) }, color: 0xE8ECEB, alpha: alpha))
                }
            }
        }
        func scan(back: Bool) {
            guard cycle > 1.85 && cycle < 2.7 else { return }
            let progress = min(1, max(0, (cycle - 1.85) / 0.85))
            let r = 15.05
            let y = (r - 0.3) * (1 - 2 * progress)
            let corners = [(-r,y,r),(r,y,r),(r,y,-r),(-r,y,-r)].map { project($0.0,$0.1,$0.2,160) }
            for i in 0..<4 {
                if (i < 2) == back { continue }
                let points = [corners[i], corners[(i+1)%4]]
                let opacity = sin(progress * .pi) * (back ? 0.24 : 0.95)
                if !back { marks.append(AssemblyMark(points: points, color: 0x408DFF, alpha: opacity * 0.15, stroke: true, width: 4)) }
                marks.append(AssemblyMark(points: points, color: 0x408DFF, alpha: opacity, stroke: true, width: back ? 0.65 : 1.15))
            }
        }
        for slot in -3...2 {
            let center = 160 + Double(slot) * 76 + advance
            if center < -35 || center > 355 { continue }
            let shadow = (0..<24).map { i in
                let angle = Double(i) * .pi / 12
                return AssemblyPoint(x: center + 18 * cos(angle), y: 81 + 2 * sin(angle))
            }
            marks.append(AssemblyMark(points: shadow, color: 0, alpha: 0.09))
            if slot > 0 { cube(center,14.65,eyes:0.22); continue }
            if slot == 0 { scan(back: true) }
            var parts: [(offset: (Double,Double,Double), alpha: Double)] = []
            for a in -1...1 { for b in -1...1 { for c in -1...1 {
                if slot < 0 && b != -1 { continue }
                let block = (a+1)*3+c+1
                let layerDelay = b == 1 ? 0.18 + random(cycleID,block,1)*0.08 : 0
                let start = 0.4 + random(cycleID,block,0)*0.28 + layerDelay
                let length = 0.30 + random(cycleID,block+b*9,2)*0.12
                let upper = b != -1
                let fall = min(1,max(0,(cycle-start-0.08)/length))
                let drop = upper ? (1-fall*fall*fall)*(22+random(cycleID,block+b*9,3)*10) : 0
                let alpha = (upper ? ease((cycle-start)/0.09) : 1) * (slot == 0 ? 1-shell : 1)
                parts.append(((Double(a)*9.85,Double(b)*9.85+drop,Double(c)*9.85),alpha))
            } } }
            parts.sort { rotate($0.offset.0,$0.offset.1,$0.offset.2).2 < rotate($1.offset.0,$1.offset.1,$1.offset.2).2 }
            for part in parts { cube(center,4.8,offset:part.offset,alpha:part.alpha) }
            if slot == 0 { cube(center,14.65,alpha:shell,eyes:0.22*awake); scan(back:false) }
        }
        return marks
    }
}
