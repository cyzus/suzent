import SwiftUI
import SuzentCore
import MarkdownUI

extension Color {
    init(presentation value: UInt32) {
        self.init(.sRGB, red: Double((value >> 16) & 255) / 255,
                  green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255, opacity: 1)
    }
}

struct MessageView: View {
    let message: DisplayMessage
    private var user: Bool { message.role == "user" }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !message.text.isEmpty {
                if message.role == "assistant" {
                    SuzentAssistantBadge()
                } else {
                    Text(user ? String(localized: "You") : String(localized: "Activity"))
                        .font(.caption.bold())
                }
                if user { Text(message.text).font(.system(size: PresentationTokens.typeChat)).textSelection(.enabled) }
            }
            if !user { ActivityContent(parts: message.parts, live: false) }

        }
        .padding(user ? 10 : 0)
        .foregroundStyle(user ? Color.black : Color.primary)
        .background {
            if user {
                Rectangle().fill(Color(presentation: PresentationTokens.code_bg))
                    .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                    .shadow(color: .primary, radius: 0, x: PresentationTokens.shadowOffset, y: PresentationTokens.shadowOffset)
            }
        }
        .padding(.leading, user ? 40 : 0)
        .frame(maxWidth: .infinity, alignment: user ? .trailing : .leading)
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}

struct SuzentButtonStyle: ButtonStyle {
    var prominent = false
    var compact = false
    @Environment(\.isEnabled) private var enabled
    @Environment(\.colorScheme) private var scheme

    func makeBody(configuration: Configuration) -> some View {
        let outline: Color = scheme == .dark ? .white : .black
        return configuration.label
            .font(.system(size: PresentationTokens.typeControl, weight: .semibold))
            .padding(.horizontal, compact ? PresentationTokens.spaceMedium : PresentationTokens.spacePage)
            .padding(.vertical, compact ? 8 : 12)
            .frame(maxWidth: compact ? nil : .infinity, minHeight: PresentationTokens.controlHeight)
            .foregroundStyle(prominent ? .white : outline)
            .background(prominent ? Color(presentation: PresentationTokens.blue)
                : scheme == .dark ? Color(presentation: PresentationTokens.surface_dark) : .white)
            .overlay(Rectangle().stroke(outline, lineWidth: PresentationTokens.borderWidth))
            .compositingGroup()
            .shadow(color: outline, radius: 0, x: configuration.isPressed ? 0 : PresentationTokens.shadowOffset,
                    y: configuration.isPressed ? 0 : PresentationTokens.shadowOffset)
            .offset(x: configuration.isPressed ? 1 : 0, y: configuration.isPressed ? 1 : 0)
            .opacity(enabled ? 1 : 0.45)
    }
}

struct SuzentWordmark: View {
    var body: some View {
        HStack(spacing: 10) {
            Rectangle().frame(width: 10, height: 10)
            Text("SUZENT").font(.system(size: PresentationTokens.typeTitle, weight: .black))
            Rectangle().frame(width: 10, height: 10)
        }.accessibilityElement(children: .ignore).accessibilityLabel("Suzent")
    }
}

struct SuzentMarkdown: View {
    let text: String
    var body: some View {
        Markdown(text)
            .markdownTheme(Theme.gitHub
                .text {
                    ForegroundColor(.primary)
                    BackgroundColor(.clear)
                    FontSize(PresentationTokens.typeChat)
                }
                .code {
                    FontFamilyVariant(.monospaced)
                    FontWeight(.semibold)
                    ForegroundColor(.black)
                    BackgroundColor(Color(presentation: PresentationTokens.yellow))
                }
                .link { ForegroundColor(Color(presentation: PresentationTokens.blue)) }
                .codeBlock { configuration in
                    VStack(alignment: .leading, spacing: 0) {
                        Text(configuration.language?.uppercased() ?? "CODE")
                            .font(.system(.caption, design: .monospaced).bold())
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12).foregroundStyle(.white).background(.black)
                        ScrollView(.horizontal) {
                            configuration.label
                                .markdownTextStyle {
                                    FontFamilyVariant(.monospaced)
                                    FontSize(14)
                                    ForegroundColor(.black)
                                    BackgroundColor(.clear)
                                }
                                .fixedSize(horizontal: true, vertical: false).padding(16)
                        }.background(Color(presentation: PresentationTokens.code_bg))
                    }.overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                        .markdownMargin(top: 8, bottom: 16)
                })
            .textSelection(.enabled)
    }
}

struct SuzentAssistantBadge: View {
    var body: some View {
        HStack(spacing: 8) {
            SuzentLogoMark().frame(width: 28, height: 28)
            Text("SUZENT").font(.system(.caption, design: .monospaced).bold())
        }.padding(.horizontal, 12).padding(.vertical, 8)
            .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
            .accessibilityElement(children: .ignore).accessibilityLabel("Suzent")
    }
}

struct ActivityContent: View {
    let parts: [MessagePart]
    var live = false
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(activityChunks(parts).enumerated()), id: \.offset) { _, chunk in
                if chunk.first?.type == "text" { SuzentMarkdown(text: chunk.first?.text ?? "") }
                else { ActivityRail(parts: chunk, live: live) }
            }
        }
    }
}

struct ActivityRail: View {
    let parts: [MessagePart]
    let live: Bool
    @State private var expanded: Bool
    init(parts: [MessagePart], live: Bool) {
        self.parts = parts; self.live = live; _expanded = State(initialValue: false)
    }
    private var waiting: Bool { parts.contains { $0.state == "approval-requested" } }
    private var running: Bool { live && parts.contains { $0.state == "running" } }
    private var failed: Bool { parts.contains { ["error", "denied"].contains($0.state ?? "") } }
    private var accent: Color { failed ? .red : running ? Color(presentation: PresentationTokens.blue) : .secondary }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { expanded.toggle() } label: {
                HStack(spacing: 10) {
                    Text(waiting ? String(localized: "Approval required") : running ? String(localized: "Running") : failed ? String(localized: "Failed") : String(localized: "Completed"))
                        .foregroundStyle(waiting || failed ? accent : .secondary)
                    Text("|").foregroundStyle(.tertiary)
                    Text("\(parts.count) steps")
                    Image(systemName: expanded ? "chevron.down" : "chevron.right").font(.system(size: 11, weight: .bold))
                    Spacer(minLength: 0)
                }.font(.system(size: 12, weight: .bold, design: .monospaced))
                    .textCase(.uppercase).foregroundStyle(.secondary)
                    .padding(.vertical, 12).padding(.horizontal, 4).contentShape(Rectangle())
            }.buttonStyle(.plain)
            if expanded {
                Rectangle().fill(Color.primary.opacity(0.12)).frame(height: 1)
                VStack(spacing: 0) {
                    ForEach(Array(parts.enumerated()), id: \.offset) { index, part in
                        ActivityRow(part: part, live: live, last: index == parts.count - 1)
                    }
                }.padding(.horizontal, 12).padding(.vertical, 8)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(Color.primary.opacity(0.12)).frame(height: 1) }
    }
}

private struct ActivityRow: View {
    let part: MessagePart
    let live: Bool
    let last: Bool
    @State private var expanded = false
    private var running: Bool { live && part.state == "running" }
    private var failed: Bool { ["error", "denied"].contains(part.state ?? "") }
    private var color: Color { failed ? .red : running ? Color(presentation: PresentationTokens.blue) : .secondary }
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(spacing: 0) {
                Text(part.state == "approval-requested" ? "!" : failed ? "×" : running ? "·" : "✓")
                    .font(.system(size: 10, weight: .bold)).frame(width: 16, height: 16)
                    .foregroundStyle(part.state == "approval-requested" ? .black : color)
                    .background(part.state == "approval-requested" ? Color(presentation: PresentationTokens.yellow) : color.opacity(0.08))
                Rectangle().fill(last ? Color.clear : Color.primary.opacity(0.12)).frame(width: 1)
            }.padding(.top, 14)
            VStack(alignment: .leading, spacing: 0) {
                Button { expanded.toggle() } label: {
                    HStack(spacing: 8) {
                        Text(part.type == "reasoning" ? String(localized: "Reasoning") : part.type == "tool" ? part.toolName ?? String(localized: "Tool activity") : String(localized: "Additional activity"))
                            .font(.system(size: 13, weight: .medium, design: part.type == "tool" ? .monospaced : .default)).lineLimit(2)
                        Spacer(minLength: 4)
                        Image(systemName: expanded ? "chevron.down" : "chevron.right").font(.system(size: 9, weight: .semibold)).foregroundStyle(.secondary)
                    }.frame(minHeight: 44).contentShape(Rectangle())
                }.buttonStyle(.plain)
                if expanded {
                    VStack(alignment: .leading, spacing: 12) {
                        detail("Input", value: part.args, code: true)
                        detail("Output", value: part.output, code: true)
                        detail("Reasoning", value: part.text, code: false)
                    }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.primary.opacity(0.04)).padding(.bottom, 12)
                }
            }
        }.fixedSize(horizontal: false, vertical: true)
    }
    @ViewBuilder private func detail(_ title: LocalizedStringKey, value: String?, code: Bool) -> some View {
        if let value, !value.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.system(size: 10, weight: .bold)).textCase(.uppercase).foregroundStyle(.secondary)
                Text(value).font(.system(size: 12, design: code ? .monospaced : .default)).textSelection(.enabled)
            }
        }
    }
}

struct ApprovalCards: View {
    let model: MobileModel
    var body: some View {
        ForEach(model.pendingApprovals) { request in
            VStack(alignment: .leading, spacing: 0) {
                Text("Approval required").font(.headline).frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12).foregroundStyle(.black).background(Color(presentation: PresentationTokens.yellow))
                VStack(alignment: .leading, spacing: 10) {
                    Text(request.toolName).font(.system(.headline, design: .monospaced))
                    Text("Via connected desktop").font(.caption).foregroundStyle(.secondary)
                    Text(request.args).font(.system(.footnote, design: .monospaced)).textSelection(.enabled)
                    if !request.reason.isEmpty { Text(request.reason).font(.footnote) }
                    if model.device?.permissions.approveTools == true && !request.actions.isEmpty {
                        ForEach(request.actions) { action in
                            Button { Task { await model.chooseApproval(request, action: action) } } label: {
                                HStack {
                                    if model.approvalChoices[request.id] == action.id { Image(systemName: "checkmark") }
                                    Text(action.behavior == "allow" ? String(localized: "Allow once") : String(localized: "Reject"))
                                }
                            }.buttonStyle(SuzentButtonStyle(prominent: action.behavior == "allow", compact: true)).disabled(model.approvalBusy)
                        }
                        Text("Choose for each pending tool to continue.").font(.caption).foregroundStyle(.secondary)
                    } else { Text("Approve on desktop, or pair again with tool approval access.").font(.footnote) }
                }.padding(12)
            }.overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
        }
    }
}


struct GreetingCube: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion || scenePhase != .active)) { timeline in
            let phase = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate * .pi / 12
            ZStack {
                Canvas { context, size in
                    context.scaleBy(x: size.width / 160, y: size.height / 160)
                    context.translateBy(x: 80, y: 80)
                    context.rotate(by: .radians(phase))
                    let rect = Path(CGRect(x: -54, y: -54, width: 108, height: 108))
                    context.stroke(rect, with: .color(.gray.opacity(0.5)), lineWidth: 1)
                    context.rotate(by: .radians(-phase * 2 + .pi / 4))
                    context.stroke(rect, with: .color(.gray.opacity(0.4)), lineWidth: 1)
                }
                cube
                    .rotation3DEffect(.degrees(sin(phase * 4) * 12), axis: (x: 0, y: 1, z: 0))
                    .rotation3DEffect(.degrees(cos(phase * 4) * 4), axis: (x: 1, y: 0, z: 0))
                    .offset(y: sin(phase * 4) * 4)
            }
        }.accessibilityHidden(true)
    }

    private var cube: some View {
        Canvas { context, size in
            context.scaleBy(x: size.width / 160, y: size.height / 160)
            func polygon(_ points: [CGPoint]) -> Path {
                Path { path in path.addLines(points); path.closeSubpath() }
            }
            let top = polygon([CGPoint(x: 28, y: 36), CGPoint(x: 95, y: 27), CGPoint(x: 143, y: 45), CGPoint(x: 65, y: 57)])
            let left = polygon([CGPoint(x: 28, y: 36), CGPoint(x: 65, y: 57), CGPoint(x: 65, y: 141), CGPoint(x: 28, y: 109)])
            let front = polygon([CGPoint(x: 65, y: 57), CGPoint(x: 143, y: 45), CGPoint(x: 138, y: 122), CGPoint(x: 65, y: 141)])
            for (face, color) in [(top, Color(white: 0.18)), (left, Color(white: 0.04)), (front, Color.black)] {
                context.fill(face, with: .color(color)); context.stroke(face, with: .color(.gray), lineWidth: 1)
            }
            for points in SuzentLogoGeometry.eyes {
                context.fill(polygon(points.map { CGPoint(x: $0.0, y: $0.1) }), with: .color(.white))
            }
        }
    }
}

struct SuzentSelectionPanel: View {
    let title: String
    let options: [(id: String, title: String)]
    let selected: String
    let choose: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(title).font(.system(size: 15, weight: .bold, design: .monospaced))
                Spacer()
                Button { dismiss() } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }.accessibilityLabel("Dismiss")
            }.padding(.leading, 16).foregroundStyle(.white).background(.black)
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(options, id: \.id) { option in
                        Button { choose(option.id); dismiss() } label: {
                            HStack(spacing: 12) {
                                Text(option.title).font(.system(size: 15, weight: option.id == selected ? .semibold : .regular)).multilineTextAlignment(.leading)
                                Spacer(minLength: 8)
                                Image(systemName: "checkmark").opacity(option.id == selected ? 1 : 0)
                            }.padding(16).frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
                                .foregroundStyle(option.id == selected ? Color.black : Color.primary)
                                .background(option.id == selected ? Color(presentation: PresentationTokens.yellow) : Color(uiColor: .systemBackground))
                        }.buttonStyle(.plain).accessibilityAddTraits(option.id == selected ? .isSelected : [])
                        Divider()
                    }
                }
            }
        }.background(Color(uiColor: .systemBackground))
            .overlay(Rectangle().stroke(.primary, lineWidth: 2))
            .shadow(color: .primary, radius: 0, x: 4, y: 4).padding(16)
            .presentationDetents([.medium, .large]).presentationDragIndicator(.hidden)
            .presentationCornerRadius(0).presentationBackground(.clear)
    }
}


struct SuzentLogoMark: View {
    var body: some View {
        Canvas { context, size in
            context.scaleBy(x: size.width / 24, y: size.height / 24)
            for (index, rect) in SuzentLogoGeometry.rectangles.enumerated() {
                context.fill(Path(roundedRect: CGRect(x: rect[0], y: rect[1], width: rect[2], height: rect[3]), cornerRadius: rect[4]), with: .color(index == 0 ? .black : .white))
            }
        }.accessibilityLabel("Suzent")
    }
}
