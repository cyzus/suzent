import SuzentCore
import SwiftUI

private struct BotInput: Equatable {
    let pending: Bool
    let startled: Bool
    let thinking: Bool
    let tool: String?
    let active: Bool
    let reduced: Bool
    let dark: Bool
    let visible: Bool
    let clicks: Int
}

struct SuzentBotBadge: View {
    let parts: [MessagePart]
    let streaming: Bool
    var toolOverride: String?
    var size: CGFloat = 32
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.scenePhase) private var scenePhase
    @State private var bot: Int32?
    @State private var time = 0.0
    @State private var frame: SuzentBotFrame?
    @State private var seenErrors: Int?
    @State private var flash = 0
    @State private var startled = false
    @State private var clicks = 0
    @State private var handledClicks = 0

    private var errors: Int { parts.filter { $0.type == "tool" && toolCallFailed($0) }.count }
    private var input: BotInput {
        let tool = toolOverride ?? robotCurrentTool(parts, streaming: streaming)
        let pending = parts.contains { $0.type == "tool" && $0.state == "approval-requested" && ($0.output ?? "").isEmpty }
        return BotInput(pending: pending, startled: startled, thinking: streaming && tool == nil, tool: tool,
                        active: streaming || pending, reduced: reduceMotion, dark: colorScheme == .dark, visible: scenePhase == .active, clicks: clicks)
    }
    var body: some View {
        Canvas { context, size in
            if let frame { drawSuzentBot(frame, in: &context, size: size) }
        }
        .frame(width: size, height: size)
        .task(id: input) {
            let config = input
            guard config.visible else { return }
            let renderer = SuzentBotRenderer.shared
            let id: Int32
            if let bot { id = bot } else {
                id = await renderer.openBot()
                guard !Task.isCancelled else { await renderer.closeBot(id); return }
                bot = id
            }
            var trick: Int? = config.clicks > handledClicks ? config.clicks - 1 : nil
            handledClicks = config.clicks
            var previous = ContinuousClock.now
            while !Task.isCancelled {
                let now = ContinuousClock.now
                time += min(durationSeconds(previous.duration(to: now)), 0.05) * 1000
                previous = now
                let next = await renderer.frame(bot: id, pending: config.pending, error: config.startled, thinking: config.thinking,
                    tool: config.tool, active: config.active, time: time, reduced: config.reduced, dark: config.dark, interactiveTrick: trick)
                guard !Task.isCancelled else { return }
                trick = nil
                frame = next
                if next.settled || config.reduced { return }
                do { try await Task.sleep(for: .seconds(max(0.001, 1.0 / 30 - durationSeconds(now.duration(to: .now))))) }
                catch { return }
            }
        }
        .onDisappear {
            if let bot { Task { await SuzentBotRenderer.shared.closeBot(bot) } }
            bot = nil
        }
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
        .contentShape(Rectangle())
        .onTapGesture { clicks += 1 }
        .accessibilityLabel(Text("Play with Suzent"))
        .accessibilityAddTraits(.isButton)
        .accessibilityAction { clicks += 1 }
    }
}

func durationSeconds(_ duration: Duration) -> Double {
    Double(duration.components.seconds) + Double(duration.components.attoseconds) / 1e18
}

struct SharedToolGlyph: View {
    let tool: String
    let animation: String
    let color: Color
    @Environment(\.accessibilityReduceMotion) private var reduced
    @Environment(\.scenePhase) private var scenePhase
    @State private var glyph: Int?
    @State private var frame: SuzentBotFrame?
    private var key: String { "\(tool)|\(animation)|\(reduced)|\(scenePhase == .active)" }
    var body: some View {
        Canvas { context, size in
            if let frame { drawSuzentBot(frame, in: &context, size: size, foreground: color) }
        }.task(id: key) {
            guard scenePhase == .active else { return }
            let renderer = SuzentBotRenderer.shared
            let id: Int
            if let glyph { id = glyph } else {
                id = await renderer.openGlyph()
                guard !Task.isCancelled else { return }
                glyph = id
            }
            let start = ContinuousClock.now
            while !Task.isCancelled {
                let now = ContinuousClock.now
                let next = await renderer.toolFrame(glyph: id, tool: tool, animation: animation,
                    seconds: durationSeconds(start.duration(to: now)), reduced: reduced)
                guard !Task.isCancelled else { return }
                frame = next
                if reduced { return }
                do { try await Task.sleep(for: .seconds(max(0.001, 1.0 / 30 - durationSeconds(now.duration(to: .now))))) }
                catch { return }
            }
        }.onDisappear {
            if let glyph { Task { await SuzentBotRenderer.shared.closeGlyph(glyph) } }
            glyph = nil
        }
    }
}

private func drawSuzentBot(_ frame: SuzentBotFrame, in context: inout GraphicsContext, size: CGSize, foreground: Color? = nil) {
    guard frame.viewBox.count >= 4, frame.viewBox[2] != 0, frame.viewBox[3] != 0 else { return }
    let minX = frame.viewBox[0], minY = frame.viewBox[1], width = frame.viewBox[2], height = frame.viewBox[3]
    context.scaleBy(x: size.width / width, y: size.height / height)
    context.translateBy(x: -minX, y: -minY)
    let fg = foreground ?? botColor(frame.fg) ?? .black
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
            let dashText = node.attrs["stroke-dasharray"] ?? ""
            let dashes: [CGFloat] = dashText.split { $0 == " " || $0 == "," }.compactMap { Double($0) }.map { CGFloat($0) }
            let phase = CGFloat(Double(node.attrs["stroke-dashoffset"] ?? "") ?? 0)
            let style = StrokeStyle(lineWidth: CGFloat(width), lineCap: .round, dash: dashes, dashPhase: phase)
            context.stroke(path, with: .color(stroke.opacity(alpha)), style: style)
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
        let radius = min(Double(node.attrs["rx"] ?? "") ?? 0, min(w, h) / 2)
        path.addPath(Path(roundedRect: CGRect(x: x, y: y, width: w, height: h), cornerRadius: radius),
                     transform: CGAffineTransform(a: matrix.a, b: matrix.b, c: matrix.c, d: matrix.d, tx: matrix.e, ty: matrix.f))
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
