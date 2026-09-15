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
                else { SuzentMarkdown(text: message.text) }
            }
            ForEach(Array(message.activities.enumerated()), id: \.offset) { _, part in
                DisclosureGroup {
                    Text([part.args, part.output, part.text].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: "\n\n")
                        .nonEmpty ?? String(localized: "View this activity on desktop."))
                        .font(.system(.footnote, design: .monospaced)).textSelection(.enabled)
                } label: {
                    Text(part.type == "tool" ? (part.toolName?.nonEmpty ?? String(localized: "Tool activity"))
                         : part.type == "reasoning" ? String(localized: "Reasoning") : String(localized: "Additional activity"))
                        .font(.subheadline)
                }.padding(12).overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
            }
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
