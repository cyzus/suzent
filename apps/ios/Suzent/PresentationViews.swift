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
            HStack(spacing: 4) {
                RoundedRectangle(cornerRadius: 1).fill(.white).frame(width: 5, height: 5)
                RoundedRectangle(cornerRadius: 1).fill(.white).frame(width: 5, height: 5)
            }.frame(width: 28, height: 28).background(.black, in: RoundedRectangle(cornerRadius: 5))
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
        self.parts = parts; self.live = live; _expanded = State(initialValue: live)
    }
    private var waiting: Bool { parts.contains { $0.state == "approval-requested" } }
    private var running: Bool { live && parts.contains { $0.state == "running" } }
    private var failed: Bool { parts.contains { ["error", "denied"].contains($0.state ?? "") } }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { expanded.toggle() } label: {
                HStack {
                    Text(expanded ? "−" : "+")
                    Text("Activity · \(parts.count)").font(.system(.subheadline, design: .monospaced))
                    Spacer()
                    Text(waiting ? String(localized: "Approval required") : running ? String(localized: "Running") : failed ? String(localized: "Failed") : String(localized: "Completed"))
                        .font(.caption).foregroundStyle(running ? Color(presentation: PresentationTokens.blue) : .secondary)
                }.padding(12).contentShape(Rectangle())
            }.buttonStyle(.plain)
            if expanded {
                ForEach(Array(parts.enumerated()), id: \.offset) { _, part in
                    ActivityRow(part: part, live: live).padding(.horizontal, 12)
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .overlay(Rectangle().stroke(.secondary.opacity(0.3), lineWidth: 1))
    }
}

private struct ActivityRow: View {
    let part: MessagePart
    let live: Bool
    @State private var expanded = false
    private var color: Color {
        if part.state == "approval-requested" { return Color(presentation: PresentationTokens.yellow) }
        if ["error", "denied"].contains(part.state ?? "") { return .red }
        if live && part.state == "running" { return Color(presentation: PresentationTokens.blue) }
        return Color(presentation: 0x62A87C)
    }
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Rectangle().fill(color.opacity(0.45)).frame(width: 2)
                .overlay(alignment: .top) { Rectangle().fill(color).frame(width: 10, height: 10).overlay(Rectangle().stroke(.primary, lineWidth: 1)).padding(.top, 15) }
                .padding(.horizontal, 4)
            VStack(alignment: .leading, spacing: 8) {
                Button { expanded.toggle() } label: {
                    HStack {
                        Text(part.type == "reasoning" ? String(localized: "Reasoning") : part.type == "tool" ? part.toolName ?? String(localized: "Tool activity") : String(localized: "Additional activity"))
                            .font(.system(.subheadline, design: .monospaced))
                        Spacer(); Text(expanded ? "−" : "+")
                    }.padding(.vertical, 10).contentShape(Rectangle())
                }.buttonStyle(.plain)
                if expanded {
                    Text([part.args, part.output, part.text].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: "\n\n"))
                        .font(.system(.footnote, design: .monospaced)).textSelection(.enabled)
                }
            }.padding(.bottom, 8)
        }.fixedSize(horizontal: false, vertical: true)
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
            // Eyes share the front face projection before the cube animation.
            context.fill(polygon([CGPoint(x: 95.334, y: 84.432), CGPoint(x: 96.236, y: 84.381), CGPoint(x: 97.066, y: 84.586), CGPoint(x: 97.770, y: 85.032), CGPoint(x: 98.300, y: 85.687), CGPoint(x: 98.621, y: 86.507), CGPoint(x: 98.711, y: 87.436), CGPoint(x: 98.405, y: 97.957), CGPoint(x: 98.261, y: 98.915), CGPoint(x: 97.894, y: 99.858), CGPoint(x: 97.328, y: 100.722), CGPoint(x: 96.601, y: 101.448), CGPoint(x: 95.762, y: 101.989), CGPoint(x: 94.867, y: 102.308), CGPoint(x: 86.343, y: 104.179), CGPoint(x: 85.432, y: 104.256), CGPoint(x: 84.584, y: 104.079), CGPoint(x: 83.859, y: 103.660), CGPoint(x: 83.306, y: 103.026), CGPoint(x: 82.964, y: 102.220), CGPoint(x: 82.858, y: 101.297), CGPoint(x: 83.025, y: 90.589), CGPoint(x: 83.163, y: 89.595), CGPoint(x: 83.537, y: 88.619), CGPoint(x: 84.122, y: 87.728), CGPoint(x: 84.877, y: 86.985), CGPoint(x: 85.750, y: 86.439), CGPoint(x: 86.681, y: 86.129)]), with: .color(.white))
            context.fill(polygon([CGPoint(x: 123.783, y: 78.852), CGPoint(x: 124.615, y: 78.810), CGPoint(x: 125.376, y: 79.015), CGPoint(x: 126.014, y: 79.452), CGPoint(x: 126.487, y: 80.090), CGPoint(x: 126.762, y: 80.886), CGPoint(x: 126.822, y: 81.786), CGPoint(x: 126.282, y: 91.968), CGPoint(x: 126.125, y: 92.895), CGPoint(x: 125.763, y: 93.804), CGPoint(x: 125.220, y: 94.636), CGPoint(x: 124.532, y: 95.334), CGPoint(x: 123.745, y: 95.850), CGPoint(x: 122.912, y: 96.150), CGPoint(x: 115.009, y: 97.885), CGPoint(x: 114.168, y: 97.951), CGPoint(x: 113.392, y: 97.773), CGPoint(x: 112.734, y: 97.360), CGPoint(x: 112.241, y: 96.742), CGPoint(x: 111.946, y: 95.958), CGPoint(x: 111.871, y: 95.064), CGPoint(x: 112.293, y: 84.706), CGPoint(x: 112.445, y: 83.746), CGPoint(x: 112.814, y: 82.805), CGPoint(x: 113.375, y: 81.949), CGPoint(x: 114.088, y: 81.236), CGPoint(x: 114.906, y: 80.716), CGPoint(x: 115.770, y: 80.424)]), with: .color(.white))
        }
    }
}
