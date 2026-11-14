import SwiftUI
import SuzentCore

private struct RailChoicesKey: EnvironmentKey {
    static let defaultValue: RailChoices? = nil
}

private struct RailScopeKey: EnvironmentKey {
    static let defaultValue = ""
}

extension EnvironmentValues {
    var railChoices: RailChoices? {
        get { self[RailChoicesKey.self] }
        set { self[RailChoicesKey.self] = newValue }
    }

    var railScope: String {
        get { self[RailScopeKey.self] }
        set { self[RailScopeKey.self] = newValue }
    }
}

private func activityToneColor(_ tone: ActivityTone) -> Color {
    switch tone {
    case .idle: return .suzentMuted
    case .streaming: return .suzentText
    case .waiting: return .orange
    case .failed: return .suzentDanger
    }
}

private let activityDisclosureAnimation = Animation.spring(duration: 0.3, bounce: 0)

/// Animates a disclosure's real height and clips its content, like Compose's expandVertically. Inserting
/// and removing views instead let removed content fade over siblings that were already sliding up.
private struct ActivityReveal<Content: View>: View {
    let expanded: Bool
    @ViewBuilder let content: () -> Content
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var height: CGFloat = 0
    @State private var rendered = false

    var body: some View {
        VStack(spacing: 0) {
            if rendered || expanded {
                content().fixedSize(horizontal: false, vertical: true)
                    .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { measured in
                        // The first measurement after opening arrives outside the toggle's transaction.
                        if expanded && height == 0 && !reduceMotion { withAnimation(activityDisclosureAnimation) { height = measured } }
                        else { height = measured }
                    }
            }
        }
        .frame(height: expanded ? height : 0, alignment: .top)
        .clipped()
        .opacity(expanded ? 1 : 0)
        .accessibilityHidden(!expanded)
        .onChange(of: expanded, initial: true) { _, open in if open { rendered = true } }
    }
}

/// Same rule as Android `turnAuthorMark`: Regent's chat header already names Regent.
enum TurnAuthorMark { case assembly, assistant }

func turnAuthorMark(regentChat: Bool, live: Bool, compact: Bool, pendingApproval: Bool) -> TurnAuthorMark? {
    if regentChat { return nil }
    return live || !compact || pendingApproval ? .assembly : .assistant
}

struct ActivityTurn: View {
    let parts: [MessagePart]
    var live = false
    var regent = false
    var compact = false
    var workedSeconds: Int?
    var citationSources: [CitationSource] = []
    var bubbleMenu: AnyView?
    @State private var expanded = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let start = activityFinalStart(parts)
        // Regent's bubbles and surfaces stay visible when the work above them folds away.
        let work = Array(parts.prefix(start)).filter { $0.regentBubble != true && $0.type != "a2ui" }
        let persistent = Array(parts.prefix(start)).filter { $0.regentBubble == true || $0.type == "a2ui" }
        let pending = work.contains { $0.state == "approval-requested" && ($0.output ?? "").isEmpty }
        let author = turnAuthorMark(regentChat: regent, live: live, compact: compact, pendingApproval: pending)
        let showDisclosure = !live && !work.isEmpty
        VStack(alignment: .leading, spacing: 10) {
            if author != nil || showDisclosure {
            HStack(spacing: 12) {
                if author == .assembly { AssemblyBadge(thinking: showAssemblyBadge(parts, streaming: live), parts: parts, streaming: live) }
                else if author == .assistant { SuzentAssistantBadge(compact: compact) }
                else { Spacer(minLength: 0) }
                if showDisclosure {
                    Button {
                        withAnimation(reduceMotion ? nil : activityDisclosureAnimation) { expanded.toggle() }
                    } label: {
                        HStack(spacing: 5) {
                            Text(workedSeconds.map { String(localized: "Worked for \(activityDuration($0))") } ?? String(localized: "Activity"))
                            Image(systemName: "chevron.right").rotationEffect(.degrees(expanded || pending ? 90 : 0))
                        }.suzentFont(PresentationTokens.typeMeta, design: .monospaced).foregroundStyle(Color.suzentMuted)
                            .frame(minHeight: 44).contentShape(Rectangle())
                    }.buttonStyle(.plain).accessibilityValue(expanded || pending ? Text("Expanded") : Text("Collapsed"))
                }
            }
            }
            if live { ActivityContent(parts: parts, live: true, citationSources: citationSources, regent: regent) }
            else {
                // The gap below the disclosed work lives inside the reveal, so a collapsed reveal adds no spacing.
                VStack(alignment: .leading, spacing: 0) {
                    ActivityReveal(expanded: expanded || pending) {
                        ActivityContent(parts: work, citationSources: citationSources, regent: regent).padding(.bottom, 10)
                    }
                    let media = mediaItems(parts)
                    if !media.isEmpty { MediaGallery(items: media).padding(.bottom, 10) }
                    ActivityContent(parts: persistent + Array(parts.dropFirst(start)), citationSources: citationSources, regent: regent,
                                    bubbleMenu: bubbleMenu)
                }
            }
            let sent = sentMediaItems(parts)
            if !sent.isEmpty { SentFilesSection(items: sent) }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .onChange(of: live) { old, new in if old && !new { expanded = false } }
    }
}

struct ActivityRail: View {
    let parts: [MessagePart]
    let live: Bool
    let current: Bool
    var expansionKey = ""
    @State private var localChoice: Bool?
    @Environment(\.railChoices) private var railChoices
    @Environment(\.railScope) private var railScope
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var storedKey: String { railChoices != nil && !railScope.isEmpty ? "\(railScope):\(expansionKey)" : "" }
    private var choice: Bool? {
        // Read the local choice even when the store already has one, so a later tap still refreshes the row.
        let local = localChoice
        if !storedKey.isEmpty, let stored = railChoices?.choice(storedKey) { return stored }
        return local
    }
    private var waiting: Bool { parts.contains { $0.state == "approval-requested" && ($0.output ?? "").isEmpty } }
    private var expanded: Bool { railExpanded(choice: choice, live: live, current: current, waiting: waiting) }
    private var running: Bool { live && current && parts.contains { $0.state == "running" || $0.type == "reasoning" } }
    private var accent: Color { activityToneColor(activityHeaderTone(parts, live: live, current: current)) }
    /// Desktop's collapsed current header: a running tool's surface, or the plain moving ruler before any tool.
    private var headerSurface: String? {
        guard live, current, !expanded, !waiting, parts.last?.type != "reasoning" else { return nil }
        if let tool = parts.last(where: { $0.type == "tool" && $0.state == "running" && ($0.output ?? "").isEmpty }) { return activityRunningSurface(tool.toolName ?? "") }
        return parts.contains { $0.type == "tool" } ? nil : "mono"
    }
    private var totals: String {
        activitySummary(parts, live: live).map { entry in
            let format: String
            switch entry.kind {
            case "running": format = String(localized: "In progress: %d")
            case "commands": format = String(localized: "Commands run: %d")
            case "read": format = String(localized: "Files read: %d")
            case "changed": format = String(localized: "Files modified: %d")
            case "searches": format = String(localized: "Searches: %d")
            case "web": format = String(localized: "Pages visited: %d")
            case "delegated": format = String(localized: "Tasks delegated: %d")
            case "agents": format = String(localized: "Agent check-ins: %d")
            case "tasks": format = String(localized: "Task updates: %d")
            case "memory": format = String(localized: "Memory updates: %d")
            case "skills": format = String(localized: "Skills used: %d")
            case "tools": format = String(localized: "Tool calls: %d")
            case "failed": format = String(localized: "Failed calls: %d")
            default: format = String(localized: "Other actions: %d")
            }
            return String(format: format, entry.count)
        }.joined(separator: " · ")
    }
    private var summary: String {
        if waiting { return String(localized: "Approval required") }
        if !running || expanded { return totals.isEmpty ? String(localized: "Reasoning") : totals }
        guard let latest = parts.last else { return String(localized: "Activity") }
        return latest.type == "reasoning" ? String(localized: "Thinking") : activityToolLabel(latest)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                let next = !expanded
                if !storedKey.isEmpty { railChoices?.set(storedKey, expanded: next) }
                withAnimation(reduceMotion ? nil : activityDisclosureAnimation) { localChoice = next }
            } label: {
                HStack(spacing: 8) {
                    if let tool = parts.last(where: { $0.type == "tool" }) { ActivityToolIcon(part: tool, running: running && tool.state == "running", color: accent).frame(width: 20, height: 20) }
                    // Desktop's collapsed header carries a streaming thought on the word itself.
                    if running && !expanded && !waiting && parts.last?.type == "reasoning" { ThinkingLabel(text: summary) }
                    else { Text(summary).lineLimit(1).truncationMode(.tail) }
                    Spacer(minLength: 0)
                    Text("\(activityStepCount(parts)) steps").suzentFont(PresentationTokens.typeSidebarSection, design: .monospaced).fixedSize()
                    Image(systemName: "chevron.right").font(.system(size: 10, weight: .semibold)).rotationEffect(.degrees(expanded ? 90 : 0))
                }.suzentFont(PresentationTokens.typeLabel, weight: .medium).foregroundStyle(accent)
                    .padding(.horizontal, 2).frame(minHeight: 44).contentShape(Rectangle())
                    .background { RunningSurface(kind: headerSurface) }
            }.buttonStyle(.plain).accessibilityValue(expanded ? Text("Expanded") : Text("Collapsed"))
                .overlay(alignment: .bottom) { Rectangle().fill(Color.suzentText.opacity(0.1)).frame(height: 1) }
                .onChange(of: storedKey) { _, _ in localChoice = nil }
            ActivityReveal(expanded: expanded) {
                VStack(spacing: 0) {
                    let rows = activityRows(parts)
                    ForEach(Array(rows.enumerated()), id: \.offset) { index, part in
                        ToolActivityBlock(part: part, live: live, first: index == 0, last: index == rows.count - 1, current: current)
                    }
                }.padding(.top, 4).padding(.bottom, 4)
            }
        }
    }
}

struct ToolActivityBlock: View {
    let part: MessagePart
    let live: Bool
    var first = true
    var last = true
    var current = true
    @State private var expanded = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var failed: Bool { activityFailed(part) }
    private var pending: Bool { part.state == "approval-requested" && (part.output ?? "").isEmpty }
    private var active: Bool { !failed && !pending && live && current && (part.state == "running" || (last && part.type == "reasoning")) }
    private var color: Color { activityToneColor(activityItemTone(failed: failed, pending: pending, active: active)) }
    private var surface: String? { part.type == "tool" && active && (part.output ?? "").isEmpty ? activityRunningSurface(part.toolName ?? "") : nil }
    private var status: String { failed ? String(localized: "Failed") : pending ? String(localized: "Approval required") : active ? String(localized: "Running") : String(localized: "Completed") }
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Color.clear.frame(width: 10)
            VStack(alignment: .leading, spacing: 0) {
                Button {
                    withAnimation(reduceMotion ? nil : activityDisclosureAnimation) { expanded.toggle() }
                } label: {
                    HStack(spacing: 8) {
                        ActivityToolIcon(part: part, running: active, color: color).frame(width: 18, height: 18)
                        VStack(alignment: .leading, spacing: 3) {
                            // Desktop names a thought "Thinking" while it streams and "Thought" once it lands.
                            if part.type == "reasoning" && active {
                                ThinkingLabel(text: String(localized: "Thinking")).suzentFont(PresentationTokens.typeLabel).foregroundStyle(Color.suzentText)
                            } else {
                                Text(part.type == "reasoning" ? String(localized: "Thought") : canonicalActivityTool(part.toolName ?? "").replacingOccurrences(of: "_", with: " "))
                                    .suzentFont(PresentationTokens.typeLabel).foregroundStyle(Color.suzentMuted).lineLimit(1)
                            }
                            if part.type == "tool" {
                                Text(activityToolLabel(part)).suzentFont(PresentationTokens.typeSidebarSection, design: .monospaced).foregroundStyle(Color.suzentMuted).lineLimit(1)
                            }
                        }
                        Spacer(minLength: 0)
                        if active || pending || failed {
                            Text(status).suzentFont(9, weight: .medium).foregroundStyle(color).lineLimit(1)
                        }
                        Image(systemName: "chevron.right").font(.system(size: 9)).rotationEffect(.degrees(expanded ? 90 : 0)).foregroundStyle(Color.suzentMuted)
                    }.padding(.horizontal, 8).frame(minHeight: 46).contentShape(Rectangle())
                        .background { RunningSurface(kind: surface) }
                        .overlay { if surface != nil { Rectangle().strokeBorder(Color.suzentText, lineWidth: 2) } }
                }.buttonStyle(.plain).accessibilityValue(Text(status))
                if !expanded && failed {
                    Text(String(activityDetail(part.output, output: true).prefix(180))).suzentFont(PresentationTokens.typeMeta, design: .monospaced)
                        .foregroundStyle(Color.suzentDanger).lineLimit(2).padding(.horizontal, 8).padding(.bottom, 8)
                }
                ActivityReveal(expanded: expanded) {
                    VStack(alignment: .leading, spacing: 12) {
                        ActivityDetailView(title: "Input", value: activityDetail(part.args), code: true)
                        ActivityDetailView(title: "Output", value: activityDetail(part.output, output: true), code: true)
                        ActivityDetailView(title: "Reasoning", value: part.text ?? "", code: false)
                    }.padding(.leading, 8).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }.fixedSize(horizontal: false, vertical: true)
            // Drawn over the block's real height so neighbouring rows join into one rail through the dot.
            .background(alignment: .topLeading) {
                GeometryReader { proxy in
                    let center: CGFloat = 23
                    Path { path in
                        if !first { path.move(to: CGPoint(x: 5, y: 0)); path.addLine(to: CGPoint(x: 5, y: center)) }
                        if !last { path.move(to: CGPoint(x: 5, y: center)); path.addLine(to: CGPoint(x: 5, y: proxy.size.height)) }
                    }.stroke(Color.suzentText.opacity(0.13), lineWidth: 1)
                    // Desktop's activity-rail-dot-pulse: fades to .45 and shrinks to .88 and back.
                    TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !active || reduceMotion)) { timeline in
                        let pulse = active && !reduceMotion ? keyframe(cycle(timeline.date.timeIntervalSinceReferenceDate, 1.2), [0, 0.5, 1], [1, 0, 1], .easeInOut) : 1
                        Circle().fill(color.opacity((active || pending || failed ? 1 : 0.35) * (0.45 + 0.55 * pulse))).frame(width: 6, height: 6)
                            .scaleEffect(0.88 + 0.12 * pulse)
                            .position(x: 5, y: center)
                    }
                }.accessibilityHidden(true)
            }
    }
}

private struct ActivityDetailView: View {
    let title: LocalizedStringKey
    let value: String
    let code: Bool
    @State private var showAll = false
    var body: some View {
        if !value.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(title).suzentFont(PresentationTokens.typeSidebarSection, weight: .semibold).textCase(.uppercase).foregroundStyle(Color.suzentMuted)
                    Spacer()
                    Button { UIPasteboard.general.string = value } label: { Image(systemName: "doc.on.doc").font(.system(size: 11)).frame(width: 44, height: 30) }
                        .buttonStyle(.plain).accessibilityLabel("Copy activity details")
                }
                let visible = showAll ? value : String(value.prefix(12000))
                ScrollView(code ? [.horizontal, .vertical] : [.vertical]) {
                    if code { Text(visible).suzentFont(PresentationTokens.typeMeta, design: .monospaced).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                    else { SuzentMarkdown(text: visible, textSize: PresentationTokens.typeLabel) }
                }.frame(maxHeight: 220)
                if value.count > 12000 && !showAll { Button("Show full details") { showAll = true }.font(.caption) }
            }
        }
    }
}

/// Desktop's ToolGroupIcon: the tool's Heroicon, moving while it runs; reasoning keeps its sparkles.
struct ActivityToolIcon: View {
    let part: MessagePart
    let running: Bool
    let color: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    private var approval: String? {
        if part.state == "approval-requested" && (part.output ?? "").isEmpty { return "pending" }
        return ["denied", "rejected"].contains(part.state ?? "") ? "denied" : nil
    }
    private var animation: String {
        part.type == "tool" ? activityToolAnimation(part.toolName ?? "", approval: approval, running: running, hasOutput: !(part.output ?? "").isEmpty) : "none"
    }
    var body: some View {
        if part.type != "tool" {
            Image(systemName: "sparkles").font(.system(size: 14)).foregroundStyle(color).accessibilityHidden(true)
        } else {
            TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion || scenePhase != .active || animation == "none")) { context in
                let pose = reduceMotion || animation == "none" ? ToolIconPose() : toolIconPose(animation, seconds: context.date.timeIntervalSinceReferenceDate)
                GeometryReader { geometry in
                    // Desktop draws these at 14px; its keyframe offsets are in those pixels.
                    let unit = geometry.size.width / 14
                    ZStack {
                        Image("Tools/\(activityToolIcon(part.toolName ?? "", approval: approval))").resizable().renderingMode(.template)
                            .foregroundStyle(color)
                            .scaleEffect(pose.scale)
                            .rotationEffect(.degrees(pose.rotation))
                            .offset(x: pose.dx * unit, y: pose.dy * unit)
                            .opacity(pose.alpha)
                        if pose.sweepAlpha > 0 {
                            Capsule().fill(color).frame(height: 1.5).padding(.horizontal, 1)
                                .offset(y: pose.sweepY * unit).opacity(pose.sweepAlpha)
                        }
                    }
                }
            }.accessibilityHidden(true)
        }
    }
}

/// Desktop's brutal-running-* background: a sliding grid (ruler ticks for "mono", dots for "dots") under a sweeping wave.
struct RunningSurface: View {
    let kind: String?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        if let kind {
            TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion || scenePhase != .active)) { timeline in
                Canvas { context, size in
                    let frame = runningSurfaceFrame(kind, seconds: reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate)
                    let ink = Color.suzentText
                    let shift = frame.gridShift.truncatingRemainder(dividingBy: 6)
                    if kind == "mono" {
                        for x in stride(from: shift - 6, to: size.width, by: 6) {
                            context.fill(Path(CGRect(x: x, y: 0, width: 1, height: size.height)), with: .color(ink.opacity(0.05)))
                        }
                    } else if kind == "dots" {
                        for x in stride(from: shift - 3, to: size.width, by: 6) {
                            for y in stride(from: 3.0, to: size.height, by: 6) {
                                context.fill(Path(ellipseIn: CGRect(x: x - 1, y: y - 1, width: 2, height: 2)), with: .color(ink.opacity(0.09)))
                            }
                        }
                    }
                    // The wave is twice the block's width and tiles, so its peak crosses the block every other half cycle.
                    let span = size.width * 2
                    let peak = frame.wave * span
                    let gradient = Gradient(stops: zip(frame.stops, frame.alphas).map { .init(color: ink.opacity($1), location: $0) })
                    for center in [peak, peak - span] {
                        let start = center - size.width
                        context.fill(Path(CGRect(x: start, y: 0, width: span, height: size.height)),
                                     with: .linearGradient(gradient, startPoint: CGPoint(x: start, y: 0), endPoint: CGPoint(x: start + span, y: 0)))
                    }
                }
            }
            .clipped()
            .accessibilityHidden(true)
        }
    }
}

/// Desktop's reasoning-thinking-label: a pale notch sweeping across the word while an ink bar wipes over it.
/// Ink is the surrounding foreground style, so callers colour it the way they colour plain text.
struct ThinkingLabel: View {
    let text: String
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        if reduceMotion {
            Text(text).lineLimit(1).truncationMode(.tail)
        } else {
            TimelineView(.animation(minimumInterval: 1.0 / 30, paused: scenePhase != .active)) { timeline in
                let frame = thinkingLabelFrame(seconds: timeline.date.timeIntervalSinceReferenceDate)
                // The sweep image is four words wide; background-position p puts its left edge at -3p of the word.
                let start = -3 * frame.sweep
                Text(text).lineLimit(1).truncationMode(.tail)
                    .hidden()
                    .overlay {
                        Rectangle().foregroundStyle(.foreground)
                            .mask(Text(text).lineLimit(1).truncationMode(.tail))
                            .mask(LinearGradient(stops: [.init(color: .black, location: 0), .init(color: .black, location: 0.4),
                                                         .init(color: .black.opacity(0.15), location: 0.47), .init(color: .black.opacity(0.15), location: 0.53),
                                                         .init(color: .black, location: 0.6), .init(color: .black, location: 1)],
                                                 startPoint: UnitPoint(x: start, y: 0.5), endPoint: UnitPoint(x: start + 4, y: 0.5)))
                    }
                    .overlay {
                        GeometryReader { proxy in
                            Rectangle().foregroundStyle(.foreground)
                                .frame(width: proxy.size.width * (frame.barEnd - frame.barStart), height: proxy.size.height * 1.3)
                                .offset(x: proxy.size.width * frame.barStart, y: -proxy.size.height * 0.15)
                        }
                    }
            }
        }
    }
}
