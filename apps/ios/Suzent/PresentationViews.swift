import SwiftUI
import SuzentCore
import MarkdownUI

extension Color {
    static var suzentSurface: Color {
        Color(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? UIColor(red: 23 / 255, green: 23 / 255, blue: 23 / 255, alpha: 1) : .white
        })
    }

    init(presentation value: UInt32) {
        self.init(.sRGB, red: Double((value >> 16) & 255) / 255,
                  green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255, opacity: 1)
    }
}

struct MessageView: View {
    let message: DisplayMessage
    var isLatest = false
    private var user: Bool { message.role == "user" }

    var body: some View {
        if user {
            HStack {
                Spacer(minLength: 40)
                Text(message.text).font(.system(size: PresentationTokens.typeChat))
                    .textSelection(.enabled).padding(PresentationTokens.spaceMedium)
                    .foregroundStyle(.black)
                    .background(Color(presentation: PresentationTokens.yellow))
                    .overlay(Rectangle().strokeBorder(.primary, lineWidth: PresentationTokens.borderWidth))
                    .background { Rectangle().fill(Color.primary).offset(x: PresentationTokens.shadowOffset, y: PresentationTokens.shadowOffset) }
                    .frame(maxWidth: 320, alignment: .trailing)
                    .padding(.trailing, PresentationTokens.shadowOffset).padding(.bottom, PresentationTokens.shadowOffset)
            }
        } else {
            VStack(alignment: .leading, spacing: 10) {
                SuzentAssistantBadge(compact: !isLatest)
                ActivityContent(parts: message.parts, live: false)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}

struct SuzentButtonStyle: ButtonStyle {
    var prominent = false
    var compact = false
    var quiet = false
    var destructive = false
    @Environment(\.isEnabled) private var enabled
    @Environment(\.colorScheme) private var scheme

    func makeBody(configuration: Configuration) -> some View {
        let outline: Color = scheme == .dark ? .white : .black
        return configuration.label
            .font(.system(size: PresentationTokens.typeControl, weight: .semibold))
            .padding(.horizontal, compact ? PresentationTokens.spaceMedium : PresentationTokens.spacePage)
            .padding(.vertical, PresentationTokens.spaceSmall)
            .frame(maxWidth: compact ? nil : .infinity, minHeight: PresentationTokens.controlHeight)
            .foregroundStyle(destructive ? Color.red : prominent ? .white : outline)
            .background(prominent ? Color(presentation: PresentationTokens.blue)
                : scheme == .dark ? Color(presentation: PresentationTokens.surface_dark) : .white)
            .overlay(Rectangle().strokeBorder(quiet ? .clear : outline, lineWidth: PresentationTokens.borderWidth))
            .compositingGroup()
            .shadow(color: quiet ? .clear : outline, radius: 0, x: configuration.isPressed ? 0 : PresentationTokens.shadowOffset,
                    y: configuration.isPressed ? 0 : PresentationTokens.shadowOffset)
            .offset(x: configuration.isPressed && !quiet ? PresentationTokens.shadowOffset : 0, y: configuration.isPressed && !quiet ? PresentationTokens.shadowOffset : 0)
            .padding(.trailing, quiet ? 0 : PresentationTokens.shadowOffset)
            .padding(.bottom, quiet ? 0 : PresentationTokens.shadowOffset)
            .opacity(enabled ? 1 : 0.45)
    }
}

struct SuzentDisclosure<Content: View>: View {
    let title: LocalizedStringKey
    @ViewBuilder let content: () -> Content
    @State private var expanded = false
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { expanded.toggle() } label: {
                HStack {
                    Text(title)
                    Spacer()
                    Text(expanded ? "−" : "+")
                }.font(.system(size: PresentationTokens.typeControl, weight: .semibold))
                    .frame(minHeight: PresentationTokens.controlHeight).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityValue(expanded ? Text("Expanded") : Text("Collapsed"))
            if expanded { content().padding(.top, PresentationTokens.spaceMedium) }
        }.padding(PresentationTokens.spacePage)
            .overlay(Rectangle().strokeBorder(.primary, lineWidth: PresentationTokens.borderWidth))
    }
}

struct SuzentTextInput: View {
    let placeholder: LocalizedStringKey
    @Binding var text: String
    var multiline = false
    @FocusState private var focused: Bool
    var body: some View {
        TextField(placeholder, text: $text, axis: multiline ? .vertical : .horizontal)
            .font(.system(size: PresentationTokens.typeControl))
            .lineLimit(multiline ? 3...6 : 1...1)
            .textInputAutocapitalization(.never).autocorrectionDisabled()
            .focused($focused).padding(PresentationTokens.spaceMedium)
            .frame(minHeight: PresentationTokens.controlHeight)
            .overlay(Rectangle().stroke(focused ? Color(presentation: PresentationTokens.blue) : .primary, lineWidth: PresentationTokens.borderWidth))
    }
}

struct SuzentNotice: View {
    let message: String
    let dismiss: () -> Void
    var body: some View {
        HStack(spacing: 12) {
            Text(message).font(.system(size: PresentationTokens.typeCaption))
            Spacer(minLength: 0)
            Button("Dismiss", action: dismiss).font(.system(size: PresentationTokens.typeCaption, weight: .semibold))
                .frame(minWidth: 44, minHeight: PresentationTokens.controlHeight).buttonStyle(.plain)
        }.padding(.horizontal, 12).padding(.vertical, 4)
            .foregroundStyle(.black).background(Color(presentation: PresentationTokens.yellow))
    }
}

struct SuzentToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button { withAnimation(.easeOut(duration: 0.15)) { configuration.isOn.toggle() } } label: {
            HStack(spacing: 12) {
                configuration.label.font(.system(size: PresentationTokens.typeControl))
                Spacer(minLength: 12)
                Rectangle().fill(configuration.isOn ? Color(presentation: PresentationTokens.blue) : Color.secondary.opacity(0.2))
                    .frame(width: 44, height: 26)
                    .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                    .overlay(alignment: configuration.isOn ? .trailing : .leading) {
                        Rectangle().fill(configuration.isOn ? .white : .primary).frame(width: 18, height: 18).padding(4)
                    }
            }.frame(minHeight: PresentationTokens.controlHeight).contentShape(Rectangle())
        }.buttonStyle(.plain)
            .accessibilityRepresentation { Toggle(isOn: configuration.$isOn) { configuration.label } }
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
    var compact = false
    var body: some View {
        Group {
            if compact {
                HStack(spacing: 6) {
                    SuzentLogoMark().frame(width: 16, height: 16).opacity(0.5)
                    Text("SUZENT").font(.system(size: 10, weight: .bold, design: .monospaced)).foregroundStyle(.secondary)
                }
            } else {
                SuzentLogoMark().frame(width: 26, height: 26)
                    .frame(width: 90, height: 40).background(Color.suzentSurface)
                    .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                    .background { Rectangle().fill(Color.primary).offset(x: 3, y: 3) }
                    .padding(.trailing, 3).padding(.bottom, 3)
            }
        }.accessibilityElement(children: .ignore).accessibilityLabel("Suzent")
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
            if live { StreamingPulse().padding(.vertical, 4).accessibilityLabel("Working…") }
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
                    if running { StreamingPulse() }
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
                        ToolActivityBlock(part: part, live: live, last: index == parts.count - 1)
                    }
                }.padding(.horizontal, 12).padding(.vertical, 8)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(Color.primary.opacity(0.12)).frame(height: 1) }
    }
}

struct ToolActivityBlock: View {
    let part: MessagePart
    let live: Bool
    var last = true
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
                        Text(part.type == "reasoning" ? String(localized: "Reasoning") : part.type == "tool" ? part.toolName?.nonEmpty ?? String(localized: "Tool activity") : String(localized: "Additional activity"))
                            .font(.system(size: 13, weight: .medium, design: part.type == "tool" ? .monospaced : .default)).lineLimit(2)
                        Spacer(minLength: 4)
                        if running { StreamingPulse() }
                        Image(systemName: expanded ? "chevron.down" : "chevron.right").font(.system(size: 9, weight: .semibold)).foregroundStyle(.secondary)
                    }.frame(minHeight: 44).contentShape(Rectangle())
                }.buttonStyle(.plain)
                if !expanded, part.type == "tool", let preview = (failed ? part.output?.nonEmpty : part.args?.nonEmpty) {
                    Text(preview).font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.secondary).lineLimit(1).padding(.bottom, 10)
                }
                if expanded {
                    VStack(alignment: .leading, spacing: 12) {
                        detail("Input", value: part.args, code: true)
                        detail("Output", value: part.output, code: true)
                        detail("Reasoning", value: part.text, code: false)
                    }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                        .overlay(Rectangle().stroke(Color.primary.opacity(0.12), lineWidth: 1))
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

struct SuzentSelectionTrigger: View {
    let value: String
    var prefix: String? = nil
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if let prefix { Text(prefix).foregroundStyle(.secondary).lineLimit(1) }
                Text(value).lineLimit(1).truncationMode(.middle)
                Image(systemName: "chevron.down").font(.system(size: 12, weight: .semibold))
            }
        }.buttonStyle(SuzentButtonStyle(compact: true))
    }
}

struct SuzentSelectionPanel: View {
    let title: String
    let options: [(id: String, title: String)]
    let selected: String
    let dismiss: () -> Void
    let choose: (String) -> Void
    @AccessibilityFocusState private var titleFocused: Bool
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(title).font(.system(size: 15, weight: .bold, design: .monospaced))
                    .accessibilityAddTraits(.isHeader).accessibilityFocused($titleFocused)
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
                                .background(option.id == selected ? Color(presentation: PresentationTokens.yellow) : Color.suzentSurface)
                        }.buttonStyle(.plain).accessibilityAddTraits(option.id == selected ? .isSelected : [])
                        Divider()
                    }
                }
            }
        }.background(Color.suzentSurface)
            .overlay(Rectangle().strokeBorder(.primary, lineWidth: PresentationTokens.borderWidth))
            .background { Rectangle().fill(Color.primary).offset(x: 4, y: 4) }
            .padding(.trailing, 4).padding(.bottom, 4)
            .onAppear { titleFocused = true }
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


struct StreamingPulse: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 20, paused: reduceMotion || scenePhase != .active)) { timeline in
            let phase = timeline.date.timeIntervalSinceReferenceDate * 4
            HStack(spacing: 3) {
                ForEach(0..<3) { index in
                    Rectangle().fill(Color(presentation: PresentationTokens.blue))
                        .frame(width: 4, height: 4)
                        .opacity(reduceMotion ? 0.7 : 0.3 + 0.7 * (sin(phase - Double(index) * 0.8) + 1) / 2)
                }
            }.frame(width: 18, height: 12)
        }.accessibilityHidden(true)
    }
}
