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
                Text(user ? String(localized: "You") : message.role == "assistant" ? "Suzent" : String(localized: "Activity"))
                    .font(.caption.bold())
                if user { Text(message.text).textSelection(.enabled) }
                else { Markdown(message.text).textSelection(.enabled) }
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
                }.padding(12).overlay(Rectangle().stroke(.primary.opacity(0.4)))
            }
        }
        .padding(user ? 14 : 0)
        .frame(maxWidth: .infinity, alignment: .leading)
        .foregroundStyle(user ? Color.black : Color.primary)
        .background {
            if user {
                Rectangle().fill(Color(presentation: PresentationTokens.yellow))
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
    @Environment(\.isEnabled) private var enabled
    @Environment(\.colorScheme) private var scheme

    func makeBody(configuration: Configuration) -> some View {
        let outline: Color = scheme == .dark ? .white : .black
        return configuration.label
            .font(.headline)
            .padding(PresentationTokens.spacePage)
            .frame(maxWidth: .infinity)
            .foregroundStyle(prominent ? .black : outline)
            .background(prominent ? Color(presentation: PresentationTokens.yellow)
                : scheme == .dark ? Color(presentation: PresentationTokens.surface_dark) : .white)
            .overlay(Rectangle().stroke(outline, lineWidth: PresentationTokens.borderWidth))
            .compositingGroup()
            .shadow(color: outline, radius: 0, x: configuration.isPressed ? 0 : PresentationTokens.shadowOffset,
                    y: configuration.isPressed ? 0 : PresentationTokens.shadowOffset)
            .offset(x: configuration.isPressed ? 1 : 0, y: configuration.isPressed ? 1 : 0)
            .opacity(enabled ? 1 : 0.45)
    }
}
