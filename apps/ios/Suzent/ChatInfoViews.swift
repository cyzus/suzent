import SwiftUI
import SuzentCore

/// The desktop sidebar's plan and context sections, sized for a phone sheet or the iPad inspector column.
struct ChatInfoPanel: View {
    let model: MobileModel
    let chatID: String
    @State private var overview: ChatOverview?
    @State private var loaded = false

    private var running: Bool { model.streaming || model.selected?.isRunning == true }

    var body: some View {
        VStack(spacing: 0) {
            // Closing is the sheet's drag or the header toggle, so the title stands alone.
            Text("Conversation info").suzentFont(PresentationTokens.typeControl, weight: .semibold)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .padding(.horizontal, PresentationTokens.spacePage).padding(.top, 8)
                .accessibilityAddTraits(.isHeader)
            Rectangle().fill(Color.suzentOutline).frame(height: PresentationTokens.borderWidthHeavy)
            ScrollView {
                VStack(alignment: .leading, spacing: PresentationTokens.spaceLarge) {
                    if let overview {
                        PlanSection(overview: overview)
                        ContextSection(context: overview.context)
                    } else if loaded {
                        Text("Conversation info is unavailable right now.").foregroundStyle(Color.suzentMuted)
                    } else {
                        ProgressView().frame(maxWidth: .infinity).padding(.top, PresentationTokens.spaceLarge)
                    }
                }.padding(PresentationTokens.spacePage).frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(Color.suzentBackground)
        .foregroundStyle(Color.suzentText)
        .task(id: chatID) {
            overview = nil; loaded = false
            while !Task.isCancelled {
                let next = await model.overview(chatID)
                if Task.isCancelled { return }
                if let next { overview = next }
                loaded = true
                // The plan moves while the agent works; at rest it only changes from the desktop.
                try? await Task.sleep(for: .seconds(running ? 4 : 15))
            }
        }
    }
}

private struct InfoSectionHeader: View {
    let title: LocalizedStringKey
    var trailing: String? = nil

    var body: some View {
        VStack(spacing: 6) {
            HStack {
                Text(title).font(.system(size: PresentationTokens.typeSidebarSection, weight: .bold))
                    .tracking(1.2).textCase(.uppercase).foregroundStyle(Color.suzentMuted)
                Spacer()
                if let trailing {
                    Text(trailing).font(.system(size: PresentationTokens.typeMeta).monospaced()).foregroundStyle(Color.suzentMuted)
                }
            }
            Rectangle().fill(Color.suzentRowDivider).frame(height: 1)
        }
    }
}

private struct PlanSection: View {
    let overview: ChatOverview

    var body: some View {
        VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
            InfoSectionHeader(title: "Plan", trailing: overview.tasks.isEmpty ? nil : "\(overview.completedCount)/\(overview.tasks.count)")
            if let goal = overview.goal {
                VStack(alignment: .leading, spacing: 4) {
                    Text(goal.objective).suzentFont(PresentationTokens.typeControl, weight: .semibold)
                    HStack(spacing: 6) {
                        Text(goalStatus(goal.status)).font(.caption.weight(.semibold))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(goal.status == "active" ? Color.suzentYellow : Color.suzentSelection)
                            .foregroundStyle(goal.status == "active" ? Color.black : Color.suzentText)
                        if let turns = goal.turnsElapsed, let max = goal.maxTurns, max > 0 {
                            Text("Turn \(turns) of \(max)").font(.caption).foregroundStyle(Color.suzentMuted)
                        }
                    }
                }
            }
            if overview.tasks.isEmpty {
                if overview.goal == nil {
                    Text("No plan yet. When the agent breaks work into steps, they appear here.")
                        .font(.subheadline).foregroundStyle(Color.suzentMuted)
                }
            } else {
                PlanProgressBar(tasks: overview.tasks)
                VStack(alignment: .leading, spacing: PresentationTokens.spaceRow) {
                    ForEach(overview.tasks) { task in PlanTaskRow(task: task) }
                }
            }
        }
    }

    private func goalStatus(_ status: String) -> LocalizedStringKey {
        switch status {
        case "active": "In progress"
        case "paused": "Paused"
        case "completed": "Completed"
        default: LocalizedStringKey(status.capitalized)
        }
    }
}

private struct PlanProgressBar: View {
    let tasks: [ChatOverview.PlanTask]

    var body: some View {
        HStack(spacing: 3) {
            ForEach(tasks) { task in
                Rectangle().fill(planColor(task.status)).frame(height: 6)
            }
        }.accessibilityHidden(true)
    }
}

private func planColor(_ status: String) -> Color {
    switch status {
    case "completed": Color(presentation: PresentationTokens.green)
    case "in_progress": Color.suzentYellow
    case "blocked": Color.suzentDanger
    default: Color.suzentSelection
    }
}

private struct PlanTaskRow: View {
    let task: ChatOverview.PlanTask

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Circle().fill(planColor(task.status)).frame(width: 8, height: 8)
                .overlay(Circle().stroke(Color.suzentOutline.opacity(task.status == "pending" ? 0.4 : 0), lineWidth: 1))
            VStack(alignment: .leading, spacing: 2) {
                Text(task.title).suzentFont(PresentationTokens.typeChat)
                    .strikethrough(task.status == "cancelled")
                    .foregroundStyle(task.isDone ? Color.suzentMuted : Color.suzentText)
                if task.status == "in_progress", let active = task.activeForm, !active.isEmpty {
                    Text(active).font(.caption).foregroundStyle(Color.suzentMuted)
                } else if task.status == "blocked" {
                    Text("Waiting on an earlier step").font(.caption).foregroundStyle(Color.suzentMuted)
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityValue(statusLabel)
    }

    private var statusLabel: Text {
        switch task.status {
        case "completed": Text("Done")
        case "in_progress": Text("In progress")
        case "blocked": Text("Blocked")
        case "cancelled": Text("Cancelled")
        default: Text("Not started")
        }
    }
}

private struct ContextSection: View {
    let context: ChatOverview.Context
    private let palette: [UInt32] = [PresentationTokens.blue, PresentationTokens.green, PresentationTokens.yellow,
                                     PresentationTokens.muted_light, PresentationTokens.gray]

    var body: some View {
        VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
            InfoSectionHeader(title: "Context", trailing: context.percent.map { percentText($0) })
            if let used = context.usedTokens {
                VStack(alignment: .leading, spacing: 4) {
                    if let percent = context.percent {
                        Text(percentText(percent)).font(.system(size: PresentationTokens.typeTitle, weight: .bold).monospacedDigit())
                    }
                    Text(context.limit.map { String(localized: "\(compactTokens(used)) of \(compactTokens($0)) tokens") }
                         ?? String(localized: "\(compactTokens(used)) tokens"))
                        .font(.subheadline.monospacedDigit()).foregroundStyle(Color.suzentMuted)
                }
                if let limit = context.limit, limit > 0 { usageBar(used: used, limit: limit) }
                if !context.categories.isEmpty {
                    VStack(spacing: 8) {
                        ForEach(Array(context.categories.enumerated()), id: \.element.id) { index, category in
                            HStack(spacing: 10) {
                                Rectangle().fill(swatch(index)).frame(width: 10, height: 10)
                                    .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 1))
                                Text(categoryLabel(category.id)).font(.subheadline)
                                Spacer()
                                Text(compactTokens(category.tokens)).font(.subheadline.monospacedDigit()).foregroundStyle(Color.suzentMuted)
                            }
                        }
                    }
                }
                if let reserve = context.reserveTokens, reserve > 0 {
                    Text("\(compactTokens(reserve)) kept free for the reply and summaries.")
                        .font(.caption).foregroundStyle(Color.suzentMuted)
                }
            } else {
                Text("Context usage appears after the first reply.").font(.subheadline).foregroundStyle(Color.suzentMuted)
            }
        }
    }

    private func usageBar(used: Int, limit: Int) -> some View {
        let categoryTotal = context.categories.reduce(0) { $0 + $1.tokens }
        let filled = min(1, Double(used) / Double(limit))
        return GeometryReader { proxy in
            HStack(spacing: 0) {
                if categoryTotal > 0 {
                    ForEach(Array(context.categories.enumerated()), id: \.element.id) { index, category in
                        Rectangle().fill(swatch(index))
                            .frame(width: proxy.size.width * filled * Double(category.tokens) / Double(categoryTotal))
                    }
                } else {
                    Rectangle().fill(Color(presentation: PresentationTokens.blue)).frame(width: proxy.size.width * filled)
                }
                Spacer(minLength: 0)
            }
        }
        .frame(height: 12)
        .background(Color.suzentSelection)
        .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
        .accessibilityHidden(true)
    }

    private func swatch(_ index: Int) -> Color {
        let token = palette[index % palette.count]
        return token == PresentationTokens.yellow ? Color.suzentYellow : Color(presentation: token)
    }

    private func categoryLabel(_ id: String) -> LocalizedStringKey {
        switch id {
        case "messages": "Messages"
        case "tool_results": "Tool calls & results"
        case "system_tools": "System tools"
        case "mcp_tools": "MCP tools"
        case "system_prompt": "System instructions"
        case "skills": "Skills"
        case "memory": "Memory & project context"
        case "repository": "Repository instructions"
        default: "Other content"
        }
    }
}

private func percentText(_ percent: Double) -> String {
    percent >= 1 || percent == 0 ? "\(Int(percent.rounded()))%" : "<1%"
}

func compactTokens(_ tokens: Int) -> String {
    tokens.formatted(.number.notation(.compactName).precision(.fractionLength(0...1)))
}

/// The desktop's sidebar glyph, turned to the edge the panel opens from: a frame whose panel fills in while it is open.
struct PanelToggleIcon: View {
    enum Edge { case trailing, bottom }
    let open: Bool
    let edge: Edge

    var body: some View {
        Canvas { context, size in
            let unit = size.width / 24
            let frame = CGRect(x: 4 * unit, y: 4 * unit, width: 16 * unit, height: 16 * unit)
            let divider = (open ? 15 : 16.5) * unit
            let panel = edge == .trailing
                ? CGRect(x: divider, y: frame.minY, width: frame.maxX - divider, height: frame.height)
                : CGRect(x: frame.minX, y: divider, width: frame.width, height: frame.maxY - divider)
            if open {
                var fill = context
                fill.opacity = 0.22
                fill.fill(Path(panel), with: .foreground)
            }
            var lines = Path(roundedRect: frame, cornerRadius: 2 * unit)
            lines.move(to: CGPoint(x: panel.minX, y: panel.minY))
            lines.addLine(to: edge == .trailing ? CGPoint(x: panel.minX, y: panel.maxY) : CGPoint(x: panel.maxX, y: panel.minY))
            context.stroke(lines, with: .foreground, lineWidth: 2 * unit)
        }
        .frame(width: 24, height: 24)
        .animation(.easeInOut(duration: 0.3), value: open)
        .accessibilityHidden(true)
    }
}
