import SwiftUI
import SuzentCore

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

struct ActivityTurn: View {
    let parts: [MessagePart]
    var live = false
    var regent = false
    var compact = false
    var workedSeconds: Int?
    var citationSources: [CitationSource] = []
    @State private var expanded = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let start = activityFinalStart(parts)
        let work = Array(parts.prefix(start)).filter { $0.regentBubble != true }
        let persistent = Array(parts.prefix(start)).filter { $0.regentBubble == true }
        let pending = work.contains { $0.state == "approval-requested" && ($0.output ?? "").isEmpty }
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                if regent { RegentIdentity(working: live, showStatus: false) }
                else if live { AssemblyBadge(thinking: showAssemblyBadge(parts, streaming: live)) }
                else { SuzentAssistantBadge(compact: compact) }
                if !live && !work.isEmpty {
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
            if live { ActivityContent(parts: parts, live: true, citationSources: citationSources, regent: regent) }
            else {
                // The gap below the disclosed work lives inside the reveal, so a collapsed reveal adds no spacing.
                VStack(alignment: .leading, spacing: 0) {
                    ActivityReveal(expanded: expanded || pending) {
                        ActivityContent(parts: work, citationSources: citationSources, regent: regent).padding(.bottom, 10)
                    }
                    ActivityContent(parts: persistent + Array(parts.dropFirst(start)), citationSources: citationSources, regent: regent)
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .onChange(of: live) { old, new in if old && !new { expanded = false } }
    }
}

struct ActivityRail: View {
    let parts: [MessagePart]
    let live: Bool
    let current: Bool
    @State private var userExpanded: Bool?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var waiting: Bool { parts.contains { $0.state == "approval-requested" && ($0.output ?? "").isEmpty } }
    private var expanded: Bool { waiting || (userExpanded ?? (live && current)) }
    private var running: Bool { live && current && parts.contains { $0.state == "running" || $0.type == "reasoning" } }
    private var failed: Bool { parts.contains(where: activityFailed) }
    private var accent: Color { waiting ? .orange : failed ? Color.suzentDanger : running ? Color.suzentLink : Color.suzentMuted }
    private var totals: String {
        activitySummary(parts, live: live).map { entry in
            let format: String
            switch entry.kind {
            case "running": format = String(localized: "In progress: %d")
            case "commands": format = String(localized: "Commands run: %d")
            case "read": format = String(localized: "Files read: %d")
            case "changed": format = String(localized: "Files modified: %d")
            case "searches": format = String(localized: "Searches: %d")
            case "failed": format = String(localized: "Failed calls: %d")
            default: format = String(localized: "Other tool calls: %d")
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
                withAnimation(reduceMotion ? nil : activityDisclosureAnimation) { userExpanded = !expanded }
            } label: {
                HStack(spacing: 8) {
                    if let latest = parts.last { ActivityToolIcon(kind: activityKind(latest), active: running, pending: waiting, color: accent).frame(width: 20, height: 20) }
                    Text(summary).lineLimit(1).truncationMode(.tail)
                    Spacer(minLength: 0)
                    Text("\(activityStepCount(parts)) steps").suzentFont(PresentationTokens.typeSidebarSection, design: .monospaced).fixedSize()
                    Image(systemName: "chevron.right").font(.system(size: 10, weight: .semibold)).rotationEffect(.degrees(expanded ? 90 : 0))
                }.suzentFont(PresentationTokens.typeLabel, weight: .medium).foregroundStyle(accent)
                    .padding(.horizontal, 2).frame(minHeight: 44).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityValue(expanded ? Text("Expanded") : Text("Collapsed"))
                .overlay(alignment: .bottom) { Rectangle().fill(Color.suzentText.opacity(0.1)).frame(height: 1) }
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
    private var color: Color { failed ? Color.suzentDanger : pending ? .orange : active ? Color.suzentLink : Color.suzentMuted }
    private var status: String { failed ? String(localized: "Failed") : pending ? String(localized: "Approval required") : active ? String(localized: "Running") : String(localized: "Completed") }
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Color.clear.frame(width: 10)
            VStack(alignment: .leading, spacing: 0) {
                Button {
                    withAnimation(reduceMotion ? nil : activityDisclosureAnimation) { expanded.toggle() }
                } label: {
                    HStack(spacing: 8) {
                        ActivityToolIcon(kind: activityKind(part), active: active, pending: pending, color: color).frame(width: 18, height: 18)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(part.type == "reasoning" ? String(localized: "Reasoning") : canonicalActivityTool(part.toolName ?? "").replacingOccurrences(of: "_", with: " "))
                                .suzentFont(PresentationTokens.typeLabel).foregroundStyle(Color.suzentMuted).lineLimit(1)
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
                    Circle().fill(color.opacity(active || pending || failed ? 1 : 0.35)).frame(width: 6, height: 6)
                        .position(x: 5, y: center)
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

struct ActivityToolIcon: View {
    let kind: String
    let active: Bool
    let pending: Bool
    let color: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    private var symbol: String {
        switch kind {
        case "terminal": "terminal"
        case "read": "doc.text"
        case "edit": "square.and.pencil"
        case "search": "magnifyingglass"
        case "agent": "person.2"
        case "reasoning": "sparkles"
        default: "wrench.and.screwdriver"
        }
    }
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 20, paused: reduceMotion || scenePhase != .active || (!active && !pending))) { context in
            let t = reduceMotion ? 0 : context.date.timeIntervalSinceReferenceDate
            ZStack {
                Image(systemName: pending ? "hand.raised" : symbol).font(.system(size: 14)).foregroundStyle(color)
                    .opacity(active || pending ? 0.7 + 0.3 * sin(t * 3) : 1)
                    .rotationEffect(.degrees(active && kind == "search" && !reduceMotion ? sin(t * 3) * 12 : 0))
                if active && !reduceMotion {
                    if kind == "read" || kind == "edit" {
                        Rectangle().fill(color.opacity(0.35)).frame(width: 17, height: 2).offset(y: sin(t * 3) * 7)
                    } else if kind == "terminal" {
                        Rectangle().fill(color).frame(width: 4, height: 2).offset(x: 5, y: 5).opacity(sin(t * 5) > 0 ? 1 : 0)
                    }
                }
            }
        }.accessibilityHidden(true)
    }
}
