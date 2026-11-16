#if canImport(JavaScriptCore)
import Foundation
import JavaScriptCore

/// The desktop Suzent bot engine, hosted in JavaScriptCore so iOS draws the same scene data.
public final class SuzentBotSession: @unchecked Sendable {
    private let context = JSContext()!
    private let id: Int32

    public init(seed: UInt32 = 1) {
        context.exceptionHandler = { _, _ in }
        let url = Bundle.module.url(forResource: "suzent-bot-core", withExtension: "js")!
        let source = try! String(contentsOf: url, encoding: .utf8)
        context.evaluateScript(source)
        id = context.evaluateScript("SuzentBot.create(\(seed))").toInt32()
    }

    public func resolveStage(hasPending: Bool, isError: Bool, isThinking: Bool, tool: String?, isActive: Bool) -> String {
        var payload: [String: Any] = ["hasPending": hasPending, "isError": isError, "isThinking": isThinking, "isActive": isActive]
        if let tool { payload["toolName"] = tool }
        let data = try! JSONSerialization.data(withJSONObject: payload)
        let json = String(data: data, encoding: .utf8)!
        return context.evaluateScript("SuzentBot.resolveStage(\(jsString(json)))").toString() ?? ""
    }

    @discardableResult
    public func create(seed: UInt32, options: String) -> Int32 {
        context.evaluateScript("SuzentBot.create(\(seed), \(jsString(options)))").toInt32()
    }

    public func step(_ json: String) -> String {
        context.evaluateScript("SuzentBot.step(\(id), \(jsString(json)))").toString() ?? ""
    }

    public func step(session: Int32, _ json: String) -> String {
        context.evaluateScript("SuzentBot.step(\(session), \(jsString(json)))").toString() ?? ""
    }

    public func destroy(session: Int32) {
        context.evaluateScript("SuzentBot.destroy(\(session))")
    }

    public func frame(json: String) -> SuzentBotFrame {
        SuzentBotFrame.parse(step(json))
    }
}

private func jsString(_ value: String) -> String {
    let data = try! JSONSerialization.data(withJSONObject: [value])
    let encoded = String(data: data, encoding: .utf8)!
    return String(encoded.dropFirst().dropLast())
}

public struct SuzentBotNode: Equatable, Sendable {
    public var tag: String
    public var attrs: [String: String]
    public var opacity: Double
    public var children: [SuzentBotNode]
}

public struct SuzentBotFrame: Equatable, Sendable {
    public var viewBox: [Double]
    public var fg: String
    public var bg: String
    public var settled: Bool
    public var nodes: [SuzentBotNode]

    public static func parse(_ json: String) -> SuzentBotFrame {
        let root = try! JSONSerialization.jsonObject(with: Data(json.utf8)) as! [String: Any]
        let box = (root["viewBox"] as! String).split(separator: " ").map { Double($0) ?? 0 }
        return SuzentBotFrame(
            viewBox: box,
            fg: root["fg"] as? String ?? "#000000",
            bg: root["bg"] as? String ?? "#ffffff",
            settled: root["settled"] as? Bool ?? false,
            nodes: nodes(root["nodes"] as? [[String: Any]] ?? [])
        )
    }

    private static func nodes(_ values: [[String: Any]]) -> [SuzentBotNode] {
        values.map { item in
            let raw = item["attrs"] as? [String: Any] ?? [:]
            let attrs = raw.mapValues { "\($0)" }
            return SuzentBotNode(tag: item["tag"] as? String ?? "", attrs: attrs, opacity: item["opacity"] as? Double ?? 1, children: nodes(item["children"] as? [[String: Any]] ?? []))
        }
    }
}

public struct BotAffine: Equatable, Sendable {
    public var a: Double
    public var b: Double
    public var c: Double
    public var d: Double
    public var e: Double
    public var f: Double
    public init(a: Double = 1, b: Double = 0, c: Double = 0, d: Double = 1, e: Double = 0, f: Double = 0) {
        self.a = a; self.b = b; self.c = c; self.d = d; self.e = e; self.f = f
    }
    public static func * (l: BotAffine, r: BotAffine) -> BotAffine {
        BotAffine(a: l.a * r.a + l.c * r.b, b: l.b * r.a + l.d * r.b, c: l.a * r.c + l.c * r.d, d: l.b * r.c + l.d * r.d, e: l.a * r.e + l.c * r.f + l.e, f: l.b * r.e + l.d * r.f + l.f)
    }
    public func x(_ px: Double, _ py: Double) -> Double { a * px + c * py + e }
    public func y(_ px: Double, _ py: Double) -> Double { b * px + d * py + f }
}

public func parseBotTransform(_ value: String) -> BotAffine {
    var matrix = BotAffine()
    let pattern = #"(matrix|translate|scale|rotate)\s*\(([^)]*)\)"#
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return matrix }
    let ns = value as NSString
    for match in regex.matches(in: value, range: NSRange(location: 0, length: ns.length)) {
        let kind = ns.substring(with: match.range(at: 1))
        let nums = numbers(ns.substring(with: match.range(at: 2)))
        let next: BotAffine
        switch kind {
        case "translate": next = BotAffine(e: nums.first ?? 0, f: nums.count > 1 ? nums[1] : 0)
        case "scale": next = BotAffine(a: nums.first ?? 1, d: nums.count > 1 ? nums[1] : (nums.first ?? 1))
        case "rotate":
            let rad = (nums.first ?? 0) * .pi / 180
            let rot = BotAffine(a: cos(rad), b: sin(rad), c: -sin(rad), d: cos(rad))
            if nums.count >= 3 { next = BotAffine(e: nums[1], f: nums[2]) * rot * BotAffine(e: -nums[1], f: -nums[2]) }
            else { next = rot }
        case "matrix" where nums.count >= 6: next = BotAffine(a: nums[0], b: nums[1], c: nums[2], d: nums[3], e: nums[4], f: nums[5])
        default: next = BotAffine()
        }
        matrix = matrix * next
    }
    return matrix
}

public enum BotPathCommand: Equatable, Sendable {
    case move(Double, Double)
    case line(Double, Double)
    case cubic(Double, Double, Double, Double, Double, Double)
    case close
}

public func parseBotPath(_ d: String) -> [BotPathCommand] {
    var commands: [BotPathCommand] = []
    let chars = Array(d)
    var index = 0
    var command: Character = " "
    var cx = 0.0, cy = 0.0, sx = 0.0, sy = 0.0
    func skip() { while index < chars.count && (chars[index].isWhitespace || chars[index] == ",") { index += 1 } }
    func number() -> Double? {
        skip()
        guard index < chars.count else { return nil }
        let start = index
        if chars[index] == "+" || chars[index] == "-" { index += 1 }
        var dot = false, exp = false
        while index < chars.count {
            let ch = chars[index]
            if ch.isNumber { index += 1 }
            else if ch == "." && !dot { dot = true; index += 1 }
            else if (ch == "e" || ch == "E") && !exp {
                exp = true; dot = true; index += 1
                if index < chars.count && (chars[index] == "+" || chars[index] == "-") { index += 1 }
            } else { break }
        }
        if index == start { return nil }
        return Double(String(chars[start..<index]))
    }
    while index < chars.count {
        skip()
        if index >= chars.count { break }
        if chars[index].isLetter { command = chars[index]; index += 1 }
        let relative = command.isLowercase
        switch command.lowercased() {
        case "m":
            guard let x = number(), let y = number() else { return commands }
            cx = relative ? cx + x : x; cy = relative ? cy + y : y; sx = cx; sy = cy
            commands.append(.move(cx, cy))
            command = relative ? "l" : "L"
        case "l":
            guard let x = number(), let y = number() else { return commands }
            cx = relative ? cx + x : x; cy = relative ? cy + y : y
            commands.append(.line(cx, cy))
        case "h":
            guard let x = number() else { return commands }
            cx = relative ? cx + x : x
            commands.append(.line(cx, cy))
        case "v":
            guard let y = number() else { return commands }
            cy = relative ? cy + y : y
            commands.append(.line(cx, cy))
        case "c":
            guard let x1 = number(), let y1 = number(), let x2 = number(), let y2 = number(), let x = number(), let y = number() else { return commands }
            let ax1 = relative ? cx + x1 : x1, ay1 = relative ? cy + y1 : y1
            let ax2 = relative ? cx + x2 : x2, ay2 = relative ? cy + y2 : y2
            cx = relative ? cx + x : x; cy = relative ? cy + y : y
            commands.append(.cubic(ax1, ay1, ax2, ay2, cx, cy))
        case "q":
            guard let x1 = number(), let y1 = number(), let x = number(), let y = number() else { return commands }
            let ax = relative ? cx + x1 : x1, ay = relative ? cy + y1 : y1
            let nx = relative ? cx + x : x, ny = relative ? cy + y : y
            commands.append(.cubic(cx + 2 * (ax - cx) / 3, cy + 2 * (ay - cy) / 3, nx + 2 * (ax - nx) / 3, ny + 2 * (ay - ny) / 3, nx, ny))
            cx = nx; cy = ny
        case "a":
            guard let rx = number(), let ry = number(), let _ = number(), let large = number(), let sweep = number(), let x = number(), let y = number() else { return commands }
            let nx = relative ? cx + x : x, ny = relative ? cy + y : y
            sampleArc(&commands, cx, cy, abs(rx), abs(ry), large != 0, sweep != 0, nx, ny)
            cx = nx; cy = ny
        case "z":
            commands.append(.close); cx = sx; cy = sy
        default: break
        }
    }
    return commands
}

private func sampleArc(_ out: inout [BotPathCommand], _ x1: Double, _ y1: Double, _ rx: Double, _ ry: Double, _ large: Bool, _ sweep: Bool, _ x2: Double, _ y2: Double) {
    if rx == 0 || ry == 0 { out.append(.line(x2, y2)); return }
    let dx = (x1 - x2) / 2, dy = (y1 - y2) / 2
    var arx = rx, ary = ry, rx2 = rx * rx, ry2 = ry * ry
    let ratio = dx * dx / rx2 + dy * dy / ry2
    if ratio > 1 { arx *= sqrt(ratio); ary *= sqrt(ratio); rx2 = arx * arx; ry2 = ary * ary }
    let sign = large == sweep ? -1.0 : 1.0
    let coef = sign * sqrt(max(0, (rx2 * ry2 - rx2 * dy * dy - ry2 * dx * dx) / (rx2 * dy * dy + ry2 * dx * dx)))
    let cx = coef * arx * dy / ary + (x1 + x2) / 2
    let cy = coef * -ary * dx / arx + (y1 + y2) / 2
    func angle(_ ux: Double, _ uy: Double, _ vx: Double, _ vy: Double) -> Double {
        let dot = ux * vx + uy * vy
        let len = sqrt(ux * ux + uy * uy) * sqrt(vx * vx + vy * vy)
        var ang = acos(min(1, max(-1, dot / len)))
        if ux * vy - uy * vx < 0 { ang = -ang }
        return ang
    }
    let theta = angle(1, 0, (x1 - cx) / arx, (y1 - cy) / ary)
    var delta = angle((x1 - cx) / arx, (y1 - cy) / ary, (x2 - cx) / arx, (y2 - cy) / ary)
    if !sweep && delta > 0 { delta -= 2 * .pi }
    if sweep && delta < 0 { delta += 2 * .pi }
    let steps = max(8, Int(abs(delta) / (.pi / 8)))
    for step in 1...steps {
        let t = theta + delta * Double(step) / Double(steps)
        out.append(.line(cx + arx * cos(t), cy + ary * sin(t)))
    }
}

private func numbers(_ value: String) -> [Double] {
    guard let regex = try? NSRegularExpression(pattern: #"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"#) else { return [] }
    let ns = value as NSString
    return regex.matches(in: value, range: NSRange(location: 0, length: ns.length)).compactMap { Double(ns.substring(with: $0.range)) }
}
#endif
