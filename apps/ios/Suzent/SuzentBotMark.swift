import SuzentCore
import SwiftUI

struct SuzentBotBadge: View {
    let parts: [MessagePart]
    let streaming: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.scenePhase) private var scenePhase
    @State private var session = SuzentBotSession()
    @State private var started = Date()
    @State private var frame = SuzentBotFrame.parse(##"{"viewBox":"-46 -46 320.54 320.54","fg":"#000000","bg":"#ffffff","settled":true,"nodes":[]}"##)
    @State private var seenErrors: Int?
    @State private var flash = 0
    @State private var startled = false
    @State private var dropped = Date.distantPast

    private var pending: Bool { parts.contains { $0.type == "tool" && $0.state == "approval-requested" && ($0.output ?? "").isEmpty } }
    private var errors: Int { parts.filter { $0.type == "tool" && toolCallFailed($0) }.count }
    private var stage: String {
        let tool = robotCurrentTool(parts)
        return session.resolveStage(hasPending: pending, isError: startled, isThinking: streaming && tool == nil, tool: tool, isActive: streaming || pending)
    }

    var body: some View {
        let stage = stage
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion || scenePhase != .active)) { timeline in
            Canvas { context, size in
                drawSuzentBot(frame, in: &context, size: size)
            }
            .frame(width: 32, height: 32)
            .onChange(of: timeline.date) { _, date in
                frame = renderedFrame(at: date)
            }
        }
        .onAppear {
            frame = renderedFrame(at: started)
        }
        .onChange(of: stage) { _, _ in
            dropped = Date()
            frame = renderedFrame(at: Date())
        }
        .onChange(of: reduceMotion) { _, _ in frame = renderedFrame(at: Date()) }
        .onChange(of: colorScheme) { _, _ in frame = renderedFrame(at: Date()) }
        .scaleEffect(dropScale)
        .offset(y: dropOffset)
        .opacity(dropOpacity)
        .onChange(of: errors, initial: true) { _, count in
            if let seen = seenErrors, count > seen { flash += 1 }
            seenErrors = count
        }
        .task(id: flash) {
            guard flash > 0 else { return }
            startled = true
            try? await Task.sleep(for: .milliseconds(2600))
            guard !Task.isCancelled else { return }
            startled = false
        }
        .accessibilityHidden(true)
    }

    private func renderedFrame(at date: Date) -> SuzentBotFrame {
        session.frame(json: stepJSON(stage: stage, time: date.timeIntervalSince(started) * 1000, reduced: reduceMotion, dark: colorScheme == .dark))
    }

    private var drop: Double { reduceMotion ? 1 : min(Date().timeIntervalSince(dropped) / 0.3, 1) }
    private var dropScale: CGFloat { CGFloat(keyframe(drop, [0, 0.5, 1], [0.5, 1.05, 1], Curve(0.175, 0.885, 0.32, 1.275))) }
    private var dropOffset: CGFloat { CGFloat(keyframe(drop, [0, 0.5, 1], [15, -3, 0], Curve(0.175, 0.885, 0.32, 1.275))) }
    private var dropOpacity: Double { min(max(keyframe(drop, [0, 0.5, 1], [0, 1, 1], Curve(0.175, 0.885, 0.32, 1.275)), 0), 1) }
}

private func stepJSON(stage: String, time: Double, reduced: Bool, dark: Bool) -> String {
    #"{"stage":"\#(stage)","time":\#(time),"reducedMotion":\#(reduced),"dark":\#(dark),"size":32,"holdWhenIdle":true,"particlesEnabled":\#(!reduced),"autoMorphCycle":\#(!reduced),"isActive":true}"#
}

private func drawSuzentBot(_ frame: SuzentBotFrame, in context: inout GraphicsContext, size: CGSize) {
    guard frame.viewBox.count >= 4, frame.viewBox[2] != 0, frame.viewBox[3] != 0 else { return }
    let minX = frame.viewBox[0], minY = frame.viewBox[1], width = frame.viewBox[2], height = frame.viewBox[3]
    context.scaleBy(x: size.width / width, y: size.height / height)
    context.translateBy(x: -minX, y: -minY)
    let fg = botColor(frame.fg) ?? .black
    let bg = botColor(frame.bg) ?? .white
    drawNodes(frame.nodes, fg: fg, bg: bg, matrix: BotAffine(), opacity: 1, root: frame.nodes, context: &context)
}

private func drawNodes(_ nodes: [SuzentBotNode], fg: Color, bg: Color, matrix: BotAffine, opacity: Double, root: [SuzentBotNode], context: inout GraphicsContext) {
    for node in nodes {
        let next = matrix * parseBotTransform(node.attrs["transform"] ?? "")
        let alpha = min(1, max(0, opacity * (Double(node.attrs["opacity"] ?? "") ?? node.opacity)))
        if let raw = node.attrs["clip-path"], raw.hasPrefix("url(#"), raw.hasSuffix(")"),
           let clipNode = findNode(root, { $0.tag == "clipPath" && $0.attrs["id"] == String(raw.dropFirst(5).dropLast()) }) {
            var clipPath = Path()
            for child in clipNode.children { append(child, next, to: &clipPath) }
            var clipped = context
            clipped.clip(to: clipPath)
            drawNode(node, fg: fg, bg: bg, matrix: next, alpha: alpha, root: root, context: &clipped)
        } else {
            drawNode(node, fg: fg, bg: bg, matrix: next, alpha: alpha, root: root, context: &context)
        }
    }
}

private func drawNode(_ node: SuzentBotNode, fg: Color, bg: Color, matrix: BotAffine, alpha: Double, root: [SuzentBotNode], context: inout GraphicsContext) {
    switch node.tag {
    case "g", "defs", "clipPath", "svg":
        drawNodes(node.children, fg: fg, bg: bg, matrix: matrix, opacity: alpha, root: root, context: &context)
    case "linearGradient", "stop":
        break
    default:
        var path = Path()
        append(node, matrix, to: &path)
        if let fill = botColor(node.attrs["fill"], fg: fg, bg: bg) {
            context.fill(path, with: .color(fill.opacity(alpha)))
        }
        if let stroke = botColor(node.attrs["stroke"], fg: fg, bg: bg) {
            let width = Double(node.attrs["stroke-width"] ?? "") ?? 1
            context.stroke(path, with: .color(stroke.opacity(alpha)), style: StrokeStyle(lineWidth: width, lineCap: .round))
        }
    }
}

private func append(_ node: SuzentBotNode, _ matrix: BotAffine, to path: inout Path) {
    switch node.tag {
    case "path":
        for command in parseBotPath(node.attrs["d"] ?? "") { add(command, matrix, to: &path) }
    case "circle":
        oval(Double(node.attrs["cx"] ?? "") ?? 0, Double(node.attrs["cy"] ?? "") ?? 0, Double(node.attrs["r"] ?? "") ?? 0, Double(node.attrs["r"] ?? "") ?? 0, matrix, &path)
    case "ellipse":
        oval(Double(node.attrs["cx"] ?? "") ?? 0, Double(node.attrs["cy"] ?? "") ?? 0, Double(node.attrs["rx"] ?? "") ?? 0, Double(node.attrs["ry"] ?? "") ?? 0, matrix, &path)
    case "line":
        move(Double(node.attrs["x1"] ?? "") ?? 0, Double(node.attrs["y1"] ?? "") ?? 0, matrix, &path)
        line(Double(node.attrs["x2"] ?? "") ?? 0, Double(node.attrs["y2"] ?? "") ?? 0, matrix, &path)
    case "rect":
        let x = Double(node.attrs["x"] ?? "") ?? 0, y = Double(node.attrs["y"] ?? "") ?? 0
        let w = Double(node.attrs["width"] ?? "") ?? 0, h = Double(node.attrs["height"] ?? "") ?? 0
        move(x, y, matrix, &path); line(x + w, y, matrix, &path); line(x + w, y + h, matrix, &path); line(x, y + h, matrix, &path); path.closeSubpath()
    default:
        break
    }
}

private let kappa = 0.5522847498307936

private func oval(_ cx: Double, _ cy: Double, _ rx: Double, _ ry: Double, _ matrix: BotAffine, _ path: inout Path) {
    guard rx > 0, ry > 0 else { return }
    let kx = rx * kappa, ky = ry * kappa
    move(cx + rx, cy, matrix, &path)
    cubic(cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry, matrix, &path)
    cubic(cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy, matrix, &path)
    cubic(cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry, matrix, &path)
    cubic(cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy, matrix, &path)
    path.closeSubpath()
}

private func add(_ command: BotPathCommand, _ matrix: BotAffine, to path: inout Path) {
    switch command {
    case let .move(x, y): move(x, y, matrix, &path)
    case let .line(x, y): line(x, y, matrix, &path)
    case let .cubic(x1, y1, x2, y2, x, y): cubic(x1, y1, x2, y2, x, y, matrix, &path)
    case .close: path.closeSubpath()
    }
}

private func move(_ x: Double, _ y: Double, _ matrix: BotAffine, _ path: inout Path) {
    path.move(to: CGPoint(x: matrix.x(x, y), y: matrix.y(x, y)))
}
private func line(_ x: Double, _ y: Double, _ matrix: BotAffine, _ path: inout Path) {
    path.addLine(to: CGPoint(x: matrix.x(x, y), y: matrix.y(x, y)))
}
private func cubic(_ x1: Double, _ y1: Double, _ x2: Double, _ y2: Double, _ x: Double, _ y: Double, _ matrix: BotAffine, _ path: inout Path) {
    path.addCurve(to: CGPoint(x: matrix.x(x, y), y: matrix.y(x, y)), control1: CGPoint(x: matrix.x(x1, y1), y: matrix.y(x1, y1)), control2: CGPoint(x: matrix.x(x2, y2), y: matrix.y(x2, y2)))
}

private func botColor(_ value: String?, fg: Color = .black, bg: Color = .white) -> Color? {
    guard let value, !value.isEmpty, value != "none", !value.hasPrefix("url(") else { return nil }
    if value == "var(--fg)" { return fg }
    if value == "var(--bg)" { return bg }
    if value.hasPrefix("#") {
        let hex = String(value.dropFirst())
        guard let rgb = UInt64(hex, radix: 16) else { return fg }
        return Color(red: Double((rgb >> 16) & 0xff) / 255, green: Double((rgb >> 8) & 0xff) / 255, blue: Double(rgb & 0xff) / 255)
    }
    if value.hasPrefix("hsl") {
        let nums = value.split { !$0.isNumber && $0 != "." }.compactMap { Double($0) }
        let light = (nums.count > 2 ? nums[2] : 0) / 100
        return Color(white: light)
    }
    return fg
}

private func findNode(_ nodes: [SuzentBotNode], _ match: (SuzentBotNode) -> Bool) -> SuzentBotNode? {
    for node in nodes {
        if match(node) { return node }
        if let found = findNode(node.children, match) { return found }
    }
    return nil
}
