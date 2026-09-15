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
                if user { Text(message.text).textSelection(.enabled) }
                else if message.parts.isEmpty { SuzentMarkdown(text: message.text) }
            }
            if !user { ActivityContent(parts: message.parts.isEmpty ? message.activities : message.parts, live: false) }

        }
        .padding(user ? 14 : 0)
        .frame(maxWidth: .infinity, alignment: .leading)
        .foregroundStyle(user ? Color.black : Color.primary)
        .background {
            if user {
                Rectangle().fill(Color(presentation: PresentationTokens.code_bg))
                    .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                    .shadow(color: .primary, radius: 0, x: PresentationTokens.shadowOffset, y: PresentationTokens.shadowOffset)
            }
        }
        .padding(.leading, user ? 24 : 0)
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
            .font(.headline)
            .padding(compact ? PresentationTokens.spaceMedium : PresentationTokens.spacePage)
            .frame(maxWidth: compact ? nil : .infinity)
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
                    FontSize(PresentationTokens.typeBody)
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
