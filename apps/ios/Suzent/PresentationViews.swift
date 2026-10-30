import SwiftUI
import SuzentCore
import MarkdownUI
import SafariServices
import ImageIO

extension Color {
    static let suzentBackground = Color(uiColor: .suzentAdaptive(light: PresentationTokens.white, dark: PresentationTokens.background_dark))
    static let suzentSurface = Color(uiColor: .suzentAdaptive(light: PresentationTokens.white, dark: PresentationTokens.surface_dark))
    static let suzentText = Color(uiColor: .suzentAdaptive(light: PresentationTokens.black, dark: PresentationTokens.text_dark))
    static let suzentMuted = Color(uiColor: .suzentAdaptive(light: PresentationTokens.muted_light, dark: PresentationTokens.muted_dark))
    static let suzentOutline = Color(uiColor: .suzentAdaptive(light: PresentationTokens.black, dark: PresentationTokens.outline_dark))
    static let suzentShadow = Color(uiColor: .suzentAdaptive(light: PresentationTokens.black, dark: PresentationTokens.shadow_dark))
    static let regentUserBackground = Color(uiColor: .suzentAdaptive(light: 0xF5F5F5, dark: 0x27272A))
    static let suzentSelection = Color(uiColor: .suzentAdaptive(light: PresentationTokens.selection_light, dark: PresentationTokens.selection_dark))
    static let suzentRowDivider = Color(uiColor: .suzentAdaptive(light: PresentationTokens.selection_light, dark: PresentationTokens.selection_dark))
    static let suzentLink = Color(uiColor: .suzentAdaptive(light: PresentationTokens.blue, dark: PresentationTokens.link_dark))
    static let suzentCodeBackground = Color(uiColor: .suzentAdaptive(light: PresentationTokens.code_bg, dark: PresentationTokens.surface_dark))
    static let suzentCodeText = Color(uiColor: .suzentAdaptive(light: PresentationTokens.code_text, dark: PresentationTokens.text_dark))
    static let suzentCodeHeader = Color(uiColor: .suzentAdaptive(light: PresentationTokens.black, dark: PresentationTokens.code_header_dark))
    static let suzentDanger = Color(uiColor: .suzentAdaptive(light: PresentationTokens.danger, dark: PresentationTokens.danger_dark))
    static let suzentErrorSurface = Color(uiColor: .suzentAdaptive(light: PresentationTokens.error_surface, dark: PresentationTokens.error_surface_dark))

    init(presentation value: UInt32) {
        self.init(.sRGB, red: Double((value >> 16) & 255) / 255,
                  green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255, opacity: 1)
    }
}

private extension UIColor {
    static func suzentAdaptive(light: UInt32, dark: UInt32) -> UIColor {
        UIColor { traits in
            let value = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((value >> 16) & 255) / 255,
                           green: CGFloat((value >> 8) & 255) / 255,
                           blue: CGFloat(value & 255) / 255, alpha: 1)
        }
    }
}

/// Token-sized text that still follows Dynamic Type, scaled against the nearest text style.
private struct SuzentScaledFont: ViewModifier {
    @ScaledMetric private var size: Double
    let weight: Font.Weight
    let design: Font.Design

    init(size: Double, weight: Font.Weight, design: Font.Design, relativeTo style: Font.TextStyle?) {
        _size = ScaledMetric(wrappedValue: size, relativeTo: style ?? Self.style(for: size))
        self.weight = weight
        self.design = design
    }

    static func style(for size: Double) -> Font.TextStyle {
        switch size {
        case ..<11.5: .caption2
        case ..<12.5: .caption
        case ..<13.5: .footnote
        case ..<15.5: .subheadline
        case ..<18: .body
        case ..<21: .title3
        case ..<26: .title2
        case ..<32: .title
        default: .largeTitle
        }
    }

    func body(content: Content) -> some View { content.font(.system(size: size, weight: weight, design: design)) }
}

extension View {
    func suzentFont(_ size: Double, weight: Font.Weight = .regular, design: Font.Design = .default, relativeTo style: Font.TextStyle? = nil) -> some View {
        modifier(SuzentScaledFont(size: size, weight: weight, design: design, relativeTo: style))
    }
}

func suzentParseDate(_ raw: String) -> Date? {
    let parser = ISO8601DateFormatter()
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return parser.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
}

extension Date {
    /// Same day → time; same year → month, day and time; otherwise a short date. 12/24 h follows the system.
    var suzentStamp: String {
        let calendar = Calendar.current
        if calendar.isDateInToday(self) { return formatted(date: .omitted, time: .shortened) }
        if calendar.isDate(self, equalTo: .now, toGranularity: .year) {
            return formatted(.dateTime.month(.abbreviated).day().hour().minute())
        }
        return formatted(date: .numeric, time: .omitted)
    }
}

struct MessageView: View {
    let message: DisplayMessage
    var regent = false
    var isLatest = false
    var fallbackModel: String?
    var canRetry = false
    var canEdit = false
    var canFork = false
    var onAction: (String, String?) -> Void = { _, _ in }
    private var user: Bool { message.role == "user" }
    @Environment(\.colorScheme) private var colorScheme
    @State private var copies = 0
    @State private var copied = false
    @State private var editing = false
    @State private var edited = ""
    @State private var confirming: String?
    @State private var sourcesOpen = false
    @State private var modelDetails: String?

    var body: some View {
        VStack(spacing: 10) {
        if ["system_triggered", "trigger"].contains(message.role) {
            if let reminder = SystemReminder(message.text) {
                SystemReminderView(reminder: reminder, citationSources: message.citationSources)
            }
        } else if user {
            HStack {
                Spacer(minLength: 40)
                VStack(alignment: .trailing, spacing: PresentationTokens.spaceSmall) {
                    ForEach(Array(message.files.enumerated()), id: \.offset) { _, file in
                        AttachmentChip(name: file.filename, mimeType: file.mimeType, foreground: regent ? Color.suzentText : .black)
                    }
                    if !message.text.isEmpty { Text(message.text).suzentFont(PresentationTokens.typeChat) }
                }
                    .padding(PresentationTokens.spaceMedium)
                    .foregroundStyle(regent ? Color.suzentText : Color.black)
                    .background(regent ? Color.regentUserBackground : Color(presentation: PresentationTokens.yellow), in: RoundedRectangle(cornerRadius: regent ? PresentationTokens.radiusBubble : PresentationTokens.radius))
                    .overlay(RoundedRectangle(cornerRadius: regent ? PresentationTokens.radiusBubble : PresentationTokens.radius).strokeBorder(
                        regent ? Color.suzentText.opacity(colorScheme == .dark ? 0.14 : 0.18) : Color.suzentOutline,
                        lineWidth: regent ? 1 : PresentationTokens.borderWidth))
                    .background {
                        if !regent { Rectangle().fill(Color.suzentShadow).offset(x: PresentationTokens.shadowOffset, y: PresentationTokens.shadowOffset) }
                    }
                    .contentShape(.contextMenuPreview, RoundedRectangle(cornerRadius: regent ? PresentationTokens.radiusBubble : PresentationTokens.radius))
                    .contextMenu { menuItems }
                    .frame(maxWidth: 320, alignment: .trailing)
                    .padding(.trailing, regent ? 0 : PresentationTokens.shadowOffset).padding(.bottom, regent ? 0 : PresentationTokens.shadowOffset)
            }
        } else {
            VStack(alignment: .leading, spacing: 10) {
                ActivityTurn(parts: message.parts, regent: regent, compact: !isLatest,
                             workedSeconds: message.workedSeconds, citationSources: message.citationSources)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
        if let reaction = message.reaction, !reaction.isEmpty {
            // Tucked over the bubble's bottom edge like the desktop tapback.
            Text(reaction).suzentFont(PresentationTokens.typeCaption).padding(.horizontal, 6).padding(.vertical, 2)
                .frame(minWidth: 28, minHeight: 24)
                .background(Color.regentUserBackground, in: Capsule())
                .overlay(Capsule().strokeBorder(Color.suzentText.opacity(colorScheme == .dark ? 0.14 : 0.12), lineWidth: 1))
                .padding(.trailing, 12).padding(.top, -18)
                .frame(maxWidth: .infinity, alignment: .trailing).accessibilityLabel(Text("Regent reacted \(reaction)"))
        }
        if ["user", "assistant"].contains(message.role) {
            // Reply text stays selectable, so assistant replies take the long-press menu on this row instead.
            footer.contentShape(Rectangle()).contentShape(.contextMenuPreview, Rectangle()).contextMenu { menuItems }
        }
        }
        .sensoryFeedback(.impact(weight: .light), trigger: copies)
        .task(id: copies) {
            guard copies > 0 else { return }
            copied = true
            try? await Task.sleep(for: .seconds(1.8))
            copied = false
        }
        .alert("Model", isPresented: Binding(get: { modelDetails != nil }, set: { if !$0 { modelDetails = nil } })) {
            Button("Dismiss") { modelDetails = nil }
        } message: { Text(modelDetails ?? "") }
        .alert(confirming == "fork" ? String(localized: "Branch conversation") : String(localized: "Retry reply"),
               isPresented: Binding(get: { confirming != nil }, set: { if !$0 { confirming = nil } })) {
            Button("Cancel", role: .cancel) { confirming = nil }
            Button("Confirm") {
                if let confirming { onAction(confirming, nil) }
                confirming = nil
            }
        } message: {
            Text(confirming == "fork" ? String(localized: "Create a new conversation from this message.") : String(localized: "Replace the latest reply by running the last user message again."))
        }
        .sheet(isPresented: $editing) {
            NavigationStack {
                TextEditor(text: $edited).suzentFont(PresentationTokens.typeChat)
                    .padding(PresentationTokens.spaceMedium)
                    .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                    .padding(20)
                    .navigationTitle("Edit and resend").navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) { Button("Cancel") { editing = false } }
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Send") { onAction("edit", edited); editing = false }
                                .disabled(edited.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }
                    }
            }.presentationDetents([.medium, .large]).presentationCornerRadius(PresentationTokens.radius)
        }
        .sheet(isPresented: $sourcesOpen) {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        ForEach(message.citationSources) { source in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(source.title).font(.headline)
                                if let snippet = source.snippet, !snippet.isEmpty { Text(snippet).font(.subheadline).lineLimit(5) }
                                if let raw = source.url, let url = URL(string: raw), ["http", "https"].contains(url.scheme) {
                                    Link("Read article", destination: url)
                                }
                            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                        }
                    }.padding(20)
                }.navigationTitle("Sources").navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Dismiss") { sourcesOpen = false } } }
            }.presentationDetents([.medium, .large]).presentationCornerRadius(PresentationTokens.radius)
        }
    }

    @ViewBuilder private var menuItems: some View {
        if !message.text.isEmpty {
            Button { copy() } label: { Label("Copy", systemImage: "doc.on.doc") }
            ShareLink(item: message.text) { Label("Share", systemImage: "square.and.arrow.up") }
        }
        if canEdit { Button { startEditing() } label: { Label("Edit and resend", systemImage: "pencil") } }
        if canRetry { Button { confirming = "retry" } label: { Label("Retry reply", systemImage: "arrow.clockwise") } }
        if canFork { Button { confirming = "fork" } label: { Label("Branch conversation", systemImage: "arrow.triangle.branch") } }
        if !user && !message.citationSources.isEmpty {
            Button { sourcesOpen = true } label: { Label("Sources", systemImage: "globe") }
        }
    }

    private var footer: some View {
        HStack(spacing: 5) {
            if user { Spacer(minLength: 0) }
            if isLatest {
                if !message.text.isEmpty {
                    Button { copy() } label: { footerIcon(copied ? "checkmark" : "doc.on.doc") }
                        .accessibilityLabel(copied ? String(localized: "Copied") : String(localized: "Copy message"))
                    ShareLink(item: message.text) { footerIcon("square.and.arrow.up") }
                        .accessibilityLabel(String(localized: "Share"))
                }
                if canEdit {
                    Button { startEditing() } label: { footerIcon("pencil") }.accessibilityLabel(String(localized: "Edit and resend"))
                }
                if canRetry {
                    Button { confirming = "retry" } label: { footerIcon("arrow.clockwise") }.accessibilityLabel(String(localized: "Retry reply"))
                }
                if canFork {
                    Button { confirming = "fork" } label: { footerIcon("arrow.triangle.branch") }.accessibilityLabel(String(localized: "Branch conversation"))
                }
            }
            if !user && !message.citationSources.isEmpty {
                Button { sourcesOpen = true } label: {
                    Label("\(message.citationSources.count)", systemImage: "globe")
                        .suzentFont(PresentationTokens.typeMeta).lineLimit(1).fixedSize().frame(minHeight: 36)
                }.accessibilityLabel(Text("Sources")).accessibilityValue(Text("\(message.citationSources.count)"))
            }
            if isLatest, !user, let model = message.model ?? fallbackModel, !model.isEmpty {
                Button { modelDetails = model } label: {
                    Text(model.split(separator: "/", maxSplits: 1).last.map(String.init) ?? model)
                        .suzentFont(PresentationTokens.typeMeta, weight: .medium).lineLimit(1).truncationMode(.tail)
                        .padding(.horizontal, 6).padding(.vertical, 3)
                        .frame(maxWidth: 180, alignment: .leading)
                        .overlay(Rectangle().strokeBorder(Color.secondary.opacity(0.3)))
                }.layoutPriority(-1).accessibilityLabel(model)
                    .accessibilityHint(String(localized: "View full model name"))
            }
            HStack(spacing: 8) {
                if let raw = message.timestamp {
                    if let date = suzentParseDate(raw) { Text(date.suzentStamp) } else { Text(raw) }
                }
                if user { Text("You") }
            }.suzentFont(PresentationTokens.typeMeta).lineLimit(1).layoutPriority(1)
            if !user { Spacer(minLength: 0) }
        }.buttonStyle(.plain).foregroundStyle(Color.suzentMuted)
            .frame(maxWidth: .infinity, minHeight: isLatest ? 36 : 20, alignment: user ? .trailing : .leading)
    }

    private func footerIcon(_ name: String) -> some View {
        Image(systemName: name).font(.system(size: 13, weight: .regular))
            .frame(width: 32, height: 36).contentShape(Rectangle())
    }

    private func copy() {
        UIPasteboard.general.string = message.text
        copies += 1
    }

    private func startEditing() {
        edited = message.text
        editing = true
    }
}

private struct SystemReminderView: View {
    let reminder: SystemReminder
    let citationSources: [CitationSource]
    @State private var expanded: Bool

    init(reminder: SystemReminder, citationSources: [CitationSource]) {
        self.reminder = reminder
        self.citationSources = citationSources
        _expanded = State(initialValue: !reminder.initiallyCollapsed)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if reminder.body.isEmpty { heading }
            else {
                Button { expanded.toggle() } label: {
                    HStack(spacing: 8) {
                        heading
                        Spacer(minLength: 4)
                        Image(systemName: expanded ? "chevron.down" : "chevron.right").font(.system(size: 11))
                    }.frame(minHeight: 44).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityValue(expanded ? Text("Expanded") : Text("Collapsed"))
            }
            if expanded && !reminder.body.isEmpty {
                SuzentMarkdown(text: reminder.body, citationSources: citationSources, textSize: PresentationTokens.typeLabel)
            }
        }.foregroundStyle(Color.suzentMuted).padding(.leading, 14).padding(.vertical, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .leading) { Rectangle().fill(Color.suzentOutline.opacity(0.4)).frame(width: 3) }
    }

    private var heading: some View {
        HStack(spacing: 8) {
            Image(systemName: "clock").accessibilityHidden(true)
            Text(reminder.title).lineLimit(2).multilineTextAlignment(.leading)
        }.suzentFont(PresentationTokens.typeMeta, weight: .semibold, design: .monospaced)
    }
}

struct ChatRowButtonStyle: ButtonStyle {
    var selected: Bool
    var destructive = false
    var divider = false
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(configuration.isPressed ? (destructive ? Color.white : Color.black) : (destructive ? Color.suzentDanger : Color.primary))
            .background(configuration.isPressed ? (destructive ? Color.suzentDanger : Color(presentation: PresentationTokens.yellow)) : selected ? Color.suzentSelection : .clear)
            .overlay(alignment: .bottom) {
                if divider { Rectangle().fill(Color.suzentRowDivider).frame(height: 1) }
            }
            .opacity(enabled ? 1 : PresentationTokens.disabledAlpha)
    }
}

struct SuzentButtonStyle: ButtonStyle {
    var prominent = false
    var compact = false
    var quiet = false
    var destructive = false
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        let outline = Color.suzentOutline
        return configuration.label
            .suzentFont(PresentationTokens.typeControl, weight: .semibold)
            .padding(.horizontal, compact ? PresentationTokens.spaceMedium : PresentationTokens.spacePage)
            .padding(.vertical, PresentationTokens.spaceSmall)
            .frame(maxWidth: compact ? nil : .infinity, minHeight: PresentationTokens.controlHeight)
            .foregroundStyle(destructive ? Color.suzentDanger : prominent ? .white : Color.suzentText)
            .background(prominent ? Color(presentation: PresentationTokens.blue)
                : Color.suzentSurface)
            .overlay(Rectangle().strokeBorder(quiet ? .clear : outline, lineWidth: PresentationTokens.borderWidth))
            .compositingGroup()
            .shadow(color: quiet ? .clear : Color.suzentShadow, radius: 0, x: configuration.isPressed ? 0 : PresentationTokens.shadowOffset,
                    y: configuration.isPressed ? 0 : PresentationTokens.shadowOffset)
            .offset(x: configuration.isPressed && !quiet ? PresentationTokens.shadowOffset : 0, y: configuration.isPressed && !quiet ? PresentationTokens.shadowOffset : 0)
            .padding(.trailing, quiet ? 0 : PresentationTokens.shadowOffset)
            .padding(.bottom, quiet ? 0 : PresentationTokens.shadowOffset)
            .opacity(enabled ? 1 : PresentationTokens.disabledAlpha)
    }
}

/// Header icon control: 44 target, no border or shadow, quiet pressed fill (desktop header icons).
struct SuzentIconButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(Color.suzentText)
            .frame(width: PresentationTokens.controlHeight, height: PresentationTokens.controlHeight)
            .background(configuration.isPressed ? Color.suzentText.opacity(PresentationTokens.pressedAlpha) : Color.clear)
            .opacity(enabled ? 1 : PresentationTokens.disabledAlpha)
    }
}

/// Plain navigation row, mirroring the desktop sidebar's New chat row: icon, label, pressed fill.
struct SuzentRowButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
            .background(configuration.isPressed ? Color.suzentText.opacity(PresentationTokens.pressedAlpha) : Color.clear)
            .opacity(enabled ? 1 : PresentationTokens.disabledAlpha)
    }
}

struct SuzentTextInput: View {
    let placeholder: LocalizedStringKey
    @Binding var text: String
    var multiline = false
    @FocusState private var focused: Bool
    var body: some View {
        TextField(placeholder, text: $text, axis: multiline ? .vertical : .horizontal)
            .suzentFont(PresentationTokens.typeControl)
            .lineLimit(multiline ? 3...6 : 1...1)
            .textInputAutocapitalization(.never).autocorrectionDisabled()
            .focused($focused).padding(PresentationTokens.spaceMedium)
            .frame(minHeight: PresentationTokens.controlHeight)
            .overlay(Rectangle().stroke(focused ? Color.suzentLink : Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
    }
}

/// Transient error: square, outlined, on the error surface. Never yellow, which is reserved for accents.
struct SuzentErrorToast: View {
    let message: String
    let dismiss: () -> Void
    var body: some View {
        HStack(spacing: 12) {
            Text(message).suzentFont(PresentationTokens.typeCaption)
                .frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
            Button("Dismiss", action: dismiss).suzentFont(PresentationTokens.typeCaption, weight: .semibold)
                .frame(minWidth: 44, minHeight: PresentationTokens.controlHeight).contentShape(Rectangle()).buttonStyle(.plain)
        }.padding(.leading, 12).padding(.trailing, 8).padding(.vertical, 2)
            .foregroundStyle(Color.suzentText).background(Color.suzentErrorSurface)
            .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
            .padding(.horizontal, 12).padding(.bottom, 8)
            .accessibilityElement(children: .contain)
    }
}

struct SuzentWordmark: View {
    var body: some View {
        HStack(spacing: 10) {
            Rectangle().frame(width: 10, height: 10)
            Text("SUZENT").suzentFont(PresentationTokens.typeTitle, weight: .black)
            Rectangle().frame(width: 10, height: 10)
        }.accessibilityElement(children: .ignore).accessibilityLabel("Suzent")
    }
}

private struct CitationPreview {
    let url: URL
    let title: String
    let snippet: String
    let favicon: String?
}

@MainActor
private final class CitationIcons: ObservableObject {
    @Published var images: [String: UIImage] = [:]

    func load(_ urls: [String]) async {
        let missing = Array(Set(urls).filter { images[$0] == nil })
        for start in stride(from: 0, to: missing.count, by: 4) {
            guard !Task.isCancelled else { return }
            let batch = Array(missing[start..<min(start + 4, missing.count)])
            let loaded = await withTaskGroup(of: (String, UIImage?).self) { group in
                for raw in batch { group.addTask { (raw, await CitationIconLoader.shared.load(raw)) } }
                var result: [String: UIImage] = [:]
                for await (raw, image) in group { if let image { result[raw] = image } }
                return result
            }
            guard !Task.isCancelled else { return }
            if !loaded.isEmpty { images.merge(loaded) { _, new in new } }
        }
    }
}

private actor CitationIconLoader {
    static let shared = CitationIconLoader()
    private let cache = NSCache<NSString, UIImage>()
    private var pending: [String: Task<UIImage?, Never>] = [:]

    func load(_ raw: String) async -> UIImage? {
        if let image = cache.object(forKey: raw as NSString) { return image }
        if let task = pending[raw] { return await task.value }
        guard let url = URL(string: raw), url.scheme == "https" else { return nil }
        let task = Task { await Self.download(url) }
        pending[raw] = task
        let image = await task.value
        pending[raw] = nil
        if let image {
            cache.countLimit = 128
            cache.setObject(image, forKey: raw as NSString)
        }
        return image
    }

    private static let session = URLSession(configuration: .ephemeral)
    private nonisolated static func download(_ url: URL) async -> UIImage? {
        do {
            let (bytes, response) = try await Self.session.bytes(for: URLRequest(url: url, timeoutInterval: 8))
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
            var data = Data()
            for try await byte in bytes {
                data.append(byte)
                if data.count > 262144 { break }
            }
            guard data.count <= 262144, let source = CGImageSourceCreateWithData(data as CFData, nil),
                  let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceShouldCacheImmediately: true,
                    kCGImageSourceThumbnailMaxPixelSize: 64
                  ] as CFDictionary) else { return nil }
            return UIImage(cgImage: thumbnail)
        } catch { return nil }
    }
}

private struct CitationBrowser: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> SFSafariViewController { SFSafariViewController(url: url) }
    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}

private struct CitationParagraph: UIViewRepresentable {
    let markdown: String
    let selectedURL: URL?
    let sources: [CitationSource]
    let icons: [String: UIImage]
    let onOpen: (URL) -> Void
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    func makeCoordinator() -> Coordinator { Coordinator(onOpen: onOpen) }
    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.isEditable = false
        view.isScrollEnabled = false
        view.backgroundColor = .clear
        view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0
        view.delegate = context.coordinator
        return view
    }
    func updateUIView(_ view: UITextView, context: Context) {
        let coordinator = context.coordinator
        coordinator.onOpen = onOpen
        let dark = colorScheme == .dark
        let pointSize = UIFontMetrics(forTextStyle: .body).scaledValue(for: CGFloat(PresentationTokens.typeChat),
            compatibleWith: UITraitCollection(preferredContentSizeCategory: UIContentSizeCategory(dynamicTypeSize)))
        let iconVersions = coordinator.iconURLs.reduce(into: [String: ObjectIdentifier]()) { result, url in
            if let image = icons[url] { result[url] = ObjectIdentifier(image) }
        }
        if coordinator.markdown == markdown, coordinator.sources == sources, coordinator.dark == dark,
           coordinator.pointSize == pointSize, coordinator.iconVersions == iconVersions {
            if coordinator.selectedURL != selectedURL {
                for url in [coordinator.selectedURL, selectedURL].compactMap({ $0 }) {
                    guard let badge = coordinator.badges[url] else { continue }
                    badge.attachment.image = url == selectedURL ? badge.highlighted : badge.normal
                    view.layoutManager.invalidateDisplay(forCharacterRange: badge.range)
                }
                coordinator.selectedURL = selectedURL
            }
            return
        }
        let parsed: AttributedString
        if coordinator.markdown == markdown, let cached = coordinator.parsed { parsed = cached }
        else { parsed = (try? AttributedString(markdown: markdown, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(markdown) }
        coordinator.parsed = parsed
        coordinator.markdown = markdown
        coordinator.sources = sources
        coordinator.dark = dark
        coordinator.pointSize = pointSize
        coordinator.selectedURL = selectedURL
        coordinator.badges = [:]
        coordinator.iconURLs = []
        let result = NSMutableAttributedString(parsed)
        let all = NSRange(location: 0, length: result.length)
        let font = UIFont.systemFont(ofSize: pointSize)
        result.addAttributes([.font: font, .foregroundColor: UIColor.suzentAdaptive(light: PresentationTokens.black, dark: PresentationTokens.text_dark)], range: all)
        for run in parsed.runs {
            let range = NSRange(run.range, in: parsed)
            if run.inlinePresentationIntent?.contains(.stronglyEmphasized) == true {
                result.addAttribute(.font, value: UIFont.boldSystemFont(ofSize: font.pointSize), range: range)
            }
        }
        var links: [(NSRange, URL)] = []
        result.enumerateAttribute(.link, in: all) { value, range, _ in
            if let url = value as? URL, url.scheme == "suzent-citation" { links.append((range, url)) }
        }
        for (range, url) in links.reversed() {
            let label = String(result.attributedSubstring(from: range).string.dropFirst(3))
            let sourceID = url.lastPathComponent.split(separator: ",").first.map(String.init)
            let favicon = sources.first { $0.id == sourceID }?.favicon
            if let favicon { coordinator.iconURLs.insert(favicon) }
            let icon = favicon.flatMap { icons[$0] }
            let badgeFont = UIFont.systemFont(ofSize: font.pointSize * 0.72, weight: .medium)
            let selected = selectedURL == url
            let ink: UIColor = dark && !selected ? .white : .darkGray
            let attributes: [NSAttributedString.Key: Any] = [.font: badgeFont, .foregroundColor: ink]
            let size = (label as NSString).size(withAttributes: attributes)
            let iconSize = badgeFont.pointSize
            let bounds = CGRect(x: 0, y: 0, width: ceil(size.width) + 14 + iconSize + 4, height: ceil(size.height) + 6)
            func renderImage(selected: Bool) -> UIImage {
                let key = Coordinator.BadgeKey(label: label, dark: dark, selected: selected, icon: icon.map(ObjectIdentifier.init))
                if let cached = coordinator.badgeImages[key] { return cached }
                let image = UIGraphicsImageRenderer(size: bounds.size).image { _ in
                    let path = UIBezierPath(roundedRect: bounds.insetBy(dx: 0.5, dy: 0.5), cornerRadius: bounds.height / 2)
                    (selected ? UIColor(red: 0.74, green: 0.84, blue: 1, alpha: 1) : UIColor(white: dark ? 0.19 : 0.96, alpha: 1)).setFill()
                    path.fill()
                    UIColor(white: dark ? 0.38 : 0.8, alpha: 1).setStroke()
                    path.lineWidth = 0.5
                    path.stroke()
                    if let icon { icon.draw(in: CGRect(x: 7, y: (bounds.height - iconSize) / 2, width: iconSize, height: iconSize)) }
                    let textAttributes: [NSAttributedString.Key: Any] = [.font: badgeFont, .foregroundColor: dark && !selected ? UIColor.white : UIColor.darkGray]
                    if icon == nil { ("↗" as NSString).draw(at: CGPoint(x: 7, y: 3), withAttributes: textAttributes) }
                    (label as NSString).draw(at: CGPoint(x: 7 + iconSize + 4, y: 3), withAttributes: textAttributes)
                }
                if coordinator.badgeImages.count >= 128 { coordinator.badgeImages.removeAll() }
                coordinator.badgeImages[key] = image
                return image
            }
            let normal = renderImage(selected: false)
            let highlighted = renderImage(selected: true)
            let attachment = NSTextAttachment()
            attachment.image = selected ? highlighted : normal
            attachment.bounds = CGRect(x: 0, y: font.descender - 1, width: bounds.width, height: bounds.height)
            let badge = NSMutableAttributedString(attachment: attachment)
            badge.addAttributes([.link: url, .accessibilitySpeechSpellOut: false], range: NSRange(location: 0, length: 1))
            result.replaceCharacters(in: range, with: badge)
            coordinator.badges[url] = Coordinator.Badge(attachment: attachment, normal: normal, highlighted: highlighted, range: .init(location: 0, length: 1))
        }
        result.enumerateAttribute(.link, in: NSRange(location: 0, length: result.length)) { value, range, _ in
            if let url = value as? URL { coordinator.badges[url]?.range = range }
        }
        coordinator.iconVersions = coordinator.iconURLs.reduce(into: [:]) { versions, url in
            if let image = icons[url] { versions[url] = ObjectIdentifier(image) }
        }
        coordinator.measuredSize = nil
        view.attributedText = result
        view.linkTextAttributes = [.foregroundColor: UIColor.suzentAdaptive(light: PresentationTokens.blue, dark: PresentationTokens.link_dark)]
        view.tintColor = .clear
        view.accessibilityLabel = String(parsed.characters)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width else { return nil }
        if let cached = context.coordinator.measuredSize, cached.width == width { return cached }
        let measured = uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
        context.coordinator.measuredSize = CGSize(width: width, height: measured.height)
        return context.coordinator.measuredSize
    }
    final class Coordinator: NSObject, UITextViewDelegate {
        struct BadgeKey: Hashable {
            let label: String
            let dark: Bool
            let selected: Bool
            let icon: ObjectIdentifier?
        }
        struct Badge {
            let attachment: NSTextAttachment
            let normal: UIImage
            let highlighted: UIImage
            var range: NSRange
        }
        var markdown: String?
        var parsed: AttributedString?
        var sources: [CitationSource] = []
        var dark = false
        var pointSize: CGFloat = 0
        var selectedURL: URL?
        var iconURLs: Set<String> = []
        var iconVersions: [String: ObjectIdentifier] = [:]
        var badges: [URL: Badge] = [:]
        var badgeImages: [BadgeKey: UIImage] = [:]
        var measuredSize: CGSize?
        var onOpen: (URL) -> Void
        init(onOpen: @escaping (URL) -> Void) { self.onOpen = onOpen }
        func textView(_ textView: UITextView, shouldInteractWith URL: URL, in characterRange: NSRange, interaction: UITextItemInteraction) -> Bool {
            if ["http", "https", "suzent-citation"].contains(URL.scheme) { onOpen(URL) }
            return false
        }
    }
}

@MainActor
private final class CitationContentCache {
    private var text: String?
    private var sources: [CitationSource] = []
    private var parsed = MarkdownContent("")

    func content(_ text: String, sources: [CitationSource]) -> MarkdownContent {
        if self.text != text || self.sources != sources {
            parsed = MarkdownContent(markdownWithCitationLinks(text, sources: sources, badges: true))
            self.text = text
            self.sources = sources
        }
        return parsed
    }
}

struct SuzentMarkdown: View {
    let text: String
    var citationSources: [CitationSource] = []
    var textSize: Double = PresentationTokens.typeChat
    @State private var pendingLink: URL?
    @State private var browserLink: URL?
    @StateObject private var icons = CitationIcons()
    @State private var contentCache = CitationContentCache()
    @ScaledMetric(relativeTo: .body) private var scale: Double = 100
    var body: some View {
        Markdown(contentCache.content(text, sources: citationSources))
            .markdownTheme(suzentMarkdownTheme)
            .environment(\.openURL, OpenURLAction { url in
                guard ["http", "https", "suzent-citation"].contains(url.scheme?.lowercased()) else { return .discarded }
                pendingLink = url
                return .handled
            })
            .textSelection(.enabled)
            .task(id: citationSources.compactMap(\.favicon)) { await icons.load(citationSources.compactMap(\.favicon)) }
            .sheet(isPresented: Binding(
                get: { pendingLink != nil },
                set: { if !$0 { pendingLink = nil } }
            )) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        Text("Sources").font(.title2.bold())
                        ForEach(previewSources, id: \.url) { source in
                            VStack(alignment: .leading, spacing: 12) {
                                HStack(spacing: 8) {
                                    if let favicon = source.favicon, let image = icons.images[favicon] {
                                        Image(uiImage: image).resizable().scaledToFit().frame(width: 18, height: 18).accessibilityHidden(true)
                                    } else { Image(systemName: "globe").frame(width: 18, height: 18).accessibilityHidden(true) }
                                    Text((source.url.host ?? "").replacingOccurrences(of: "www.", with: ""))
                                }.font(.caption).foregroundStyle(Color.suzentMuted)
                                Text(source.title).font(.headline)
                                if !source.snippet.isEmpty { Text(source.snippet).font(.subheadline).lineLimit(6) }
                                Button("Read article") { browserLink = source.url }.buttonStyle(SuzentButtonStyle(prominent: true, compact: true))
                                HStack {
                                    Button("Copy link") { UIPasteboard.general.url = source.url }
                                    Spacer()
                                    Button("Open externally") { UIApplication.shared.open(source.url) }
                                }.font(.caption)
                            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                        }
                    }.padding(24)
                }
                .presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
                .presentationCornerRadius(PresentationTokens.radius)
                .sheet(isPresented: Binding(get: { browserLink != nil }, set: { if !$0 { browserLink = nil } })) {
                    if let browserLink { CitationBrowser(url: browserLink).ignoresSafeArea() }
                }
            }
    }

    private var previewSources: [CitationPreview] {
        guard let link = pendingLink else { return [] }
        if link.scheme == "suzent-citation" {
            return link.lastPathComponent.split(separator: ",").compactMap { id in
                guard let source = citationSources.first(where: { $0.id == id }), let raw = source.url,
                      let url = URL(string: raw), ["http", "https"].contains(url.scheme) else { return nil }
                return CitationPreview(url: url, title: source.title, snippet: source.snippet ?? "", favicon: source.favicon)
            }
        }
        let source = citationSources.first { $0.url == link.absoluteString }
        return [CitationPreview(url: link, title: source?.title ?? link.host ?? link.absoluteString, snippet: source?.snippet ?? "", favicon: source?.favicon)]
    }

    private var suzentMarkdownTheme: Theme {
        Theme.gitHub
                .paragraph { configuration in
                    if configuration.content.renderMarkdown().contains("suzent-citation://") {
                        CitationParagraph(markdown: configuration.content.renderMarkdown(), selectedURL: pendingLink, sources: citationSources, icons: icons.images) { pendingLink = $0 }
                    } else { configuration.label }
                }
                .text {
                    ForegroundColor(Color.suzentText)
                    BackgroundColor(.clear)
                    FontSize(textSize * scale / 100)
                }
                .code {
                    FontFamilyVariant(.monospaced)
                    FontWeight(.semibold)
                    ForegroundColor(.black)
                    BackgroundColor(Color(presentation: PresentationTokens.yellow))
                }
                .link {
                    ForegroundColor(Color.suzentLink)
                }
                .codeBlock { configuration in
                    VStack(alignment: .leading, spacing: 0) {
                        Text(configuration.language?.uppercased() ?? "CODE")
                            .font(.system(.caption, design: .monospaced).bold())
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12).foregroundStyle(.white).background(Color.suzentCodeHeader)
                        ScrollView(.horizontal) {
                            configuration.label
                                .markdownTextStyle {
                                    FontFamilyVariant(.monospaced)
                                    FontSize(14 * scale / 100)
                                    ForegroundColor(Color.suzentCodeText)
                                    BackgroundColor(.clear)
                                }
                                .fixedSize(horizontal: true, vertical: false).padding(16)
                        }.background(Color.suzentCodeBackground)
                    }.overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                        .markdownMargin(top: 8, bottom: 16)
                }
    }
}

struct SuzentAssistantBadge: View {
    var compact = false
    var body: some View {
        Group {
            if compact {
                HStack(spacing: 6) {
                    SuzentLogoMark().frame(width: 16, height: 16).opacity(0.5)
                    Text("SUZENT").suzentFont(PresentationTokens.typeSidebarSection, weight: .bold, design: .monospaced).foregroundStyle(Color.suzentMuted)
                }
            } else {
                SuzentLogoMark().frame(width: 26, height: 26)
                    .frame(width: 90, height: 40).background(Color.suzentSurface)
                    .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                    .background { Rectangle().fill(Color.suzentShadow).offset(x: PresentationTokens.shadowOffsetOverlay, y: PresentationTokens.shadowOffsetOverlay) }
                    .padding(.trailing, PresentationTokens.shadowOffsetOverlay).padding(.bottom, PresentationTokens.shadowOffsetOverlay)
            }
        }.accessibilityElement(children: .ignore).accessibilityLabel("Suzent")
    }
}

struct ActivityContent: View {
    let parts: [MessagePart]
    var live = false
    var citationSources: [CitationSource] = []
    var regent = false
    var body: some View {
        let chunks = activityChunks(parts)
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(chunks.enumerated()), id: \.offset) { index, chunk in
                if chunk.first?.type == "text" {
                    SuzentMarkdown(text: chunk.first?.text ?? "", citationSources: citationSources)
                        .padding(regent ? 12 : 0)
                        .background(regent ? Color.suzentText.opacity(0.045) : Color.clear, in: RoundedRectangle(cornerRadius: PresentationTokens.radiusBubble))
                }
                else { ActivityRail(parts: chunk, live: live, current: index == chunks.count - 1) }
            }
        }
    }
}

struct ApprovalCards: View {
    let model: MobileModel
    var body: some View {
        VStack(spacing: 8) {
            ForEach(model.pendingApprovals) { request in ApprovalCard(model: model, request: request) }
        }
    }
}

private struct ApprovalCard: View {
    let model: MobileModel
    let request: ApprovalRequest
    @State private var showAll = false
    @State private var choices = 0
    @State private var allowed = false
    private var long: Bool { request.args.count > 160 || request.args.split(separator: "\n", omittingEmptySubsequences: false).count > 3 }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Approval required").font(.headline).frame(maxWidth: .infinity, alignment: .leading)
                .padding(12).foregroundStyle(.black).background(Color(presentation: PresentationTokens.yellow))
            VStack(alignment: .leading, spacing: 10) {
                Text(request.toolName).font(.system(.headline, design: .monospaced))
                Text("Via connected desktop").font(.caption).foregroundStyle(Color.suzentMuted)
                Text(request.args).font(.system(.footnote, design: .monospaced)).textSelection(.enabled)
                    .lineLimit(showAll ? nil : 3)
                if long {
                    Button(showAll ? String(localized: "Show less") : String(localized: "Show all")) { showAll.toggle() }
                        .font(.caption.bold()).foregroundStyle(Color.suzentText).buttonStyle(.plain).frame(minHeight: 44)
                }
                if !request.reason.isEmpty { Text(request.reason).font(.footnote) }
                if model.device?.permissions.approveTools == true && !request.actions.isEmpty {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 12) { choiceButtons }
                        VStack(alignment: .leading, spacing: 12) { choiceButtons }
                    }
                    Text("Choose for each pending tool to continue.").font(.caption).foregroundStyle(Color.suzentMuted)
                } else { Text("Approve on desktop, or pair again with tool approval access.").font(.footnote) }
            }.padding(12)
        }.background(Color.suzentSurface)
            .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
            .sensoryFeedback(trigger: choices) { _, _ in allowed ? .success : .warning }
    }

    private var choiceButtons: some View {
        ForEach(request.actions) { action in
            Button {
                allowed = action.behavior == "allow"
                choices += 1
                Task { await model.chooseApproval(request, action: action) }
            } label: {
                HStack {
                    if model.approvalChoices[request.id] == action.id { Image(systemName: "checkmark") }
                    Text(action.behavior == "allow" ? String(localized: "Allow once") : String(localized: "Reject"))
                }
            }.buttonStyle(SuzentButtonStyle(prominent: action.behavior == "allow", compact: true)).disabled(model.approvalBusy)
        }
    }
}


struct GreetingCube: View {
    let engaged: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.colorScheme) private var colorScheme
    @State private var started = Date()

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion || scenePhase != .active)) { timeline in
            Canvas { context, size in
                context.scaleBy(x: size.width / 160, y: size.height / 160)
                let ink: UInt32 = colorScheme == .dark ? PresentationTokens.text_dark : PresentationTokens.black
                for mark in GreetingCubeScene.frame(seconds: timeline.date.timeIntervalSince(started), engaged: engaged, reduced: reduceMotion, inkColor: ink) {
                    var path = Path()
                    for (index, point) in mark.points.enumerated() {
                        let position = CGPoint(x: point.x, y: point.y)
                        if index == 0 { path.move(to: position) } else { path.addLine(to: position) }
                    }
                    if mark.points.count > 2 { path.closeSubpath() }
                    let shading = GraphicsContext.Shading.color(Color(presentation: mark.color).opacity(mark.alpha))
                    if mark.stroke { context.stroke(path, with: shading, lineWidth: mark.width) }
                    else { context.fill(path, with: shading) }
                }
            }
        }.accessibilityHidden(true)
    }
}

struct SuzentSelectionTrigger: View {
    let value: String
    var prefix: String? = nil
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if let prefix { Text(prefix).foregroundStyle(Color.suzentMuted).lineLimit(1) }
                Text(value).lineLimit(1).truncationMode(.middle)
                Image(systemName: "chevron.down").font(.system(size: 12, weight: .semibold))
            }
        }.buttonStyle(SuzentButtonStyle(compact: true))
    }
}

/// Picker content for a bottom sheet: black header, yellow selected row, 48 minimum rows.
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
                Text(title).suzentFont(15, weight: .bold, design: .monospaced)
                    .accessibilityAddTraits(.isHeader).accessibilityFocused($titleFocused)
                Spacer()
                Button { dismiss() } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }.accessibilityLabel("Dismiss")
            }.padding(.leading, 16).padding(.top, 12).foregroundStyle(.white).background(.black)
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(options, id: \.id) { option in
                        Button { choose(option.id); dismiss() } label: {
                            HStack(spacing: 12) {
                                Text(option.title).suzentFont(15, weight: option.id == selected ? .semibold : .regular).multilineTextAlignment(.leading)
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
            .onAppear { titleFocused = true }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
            .presentationCornerRadius(PresentationTokens.radius)
            .presentationBackground(Color.suzentSurface)
    }
}


struct SuzentLogoMark: View {
    var eyeOffset: CGSize = .zero
    var blink: Double = 1
    var body: some View {
        Canvas { context, size in
            context.scaleBy(x: size.width / 24, y: size.height / 24)
            for (index, rect) in SuzentLogoGeometry.rectangles.enumerated() {
                let eye = index > 0
                let height = rect[3] * (eye ? blink : 1)
                let bounds = CGRect(x: rect[0] + (eye ? eyeOffset.width : 0),
                                    y: rect[1] + (eye ? eyeOffset.height + (rect[3] - height) / 2 : 0),
                                    width: rect[2], height: height)
                context.fill(Path(roundedRect: bounds, cornerRadius: min(rect[4], height / 2)), with: .color(eye ? .white : .black))
            }
        }.accessibilityLabel("Suzent")
    }
}


struct ReconnectIndicator: View {
    let active: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var began = Date()

    private func sample(_ phase: Double, _ frames: [(Double, Double)]) -> Double {
        for index in 1..<frames.count where phase <= frames[index].0 {
            let (start, from) = frames[index - 1]
            let (end, to) = frames[index]
            let t = max(0, min(1, (phase - start) / (end - start)))
            return from + (to - from) * t * t * (3 - 2 * t)
        }
        return frames.last?.1 ?? 0
    }

    var body: some View {
        let animated = active && !reduceMotion && scenePhase == .active
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !animated)) { timeline in
            let p = animated ? timeline.date.timeIntervalSince(began).truncatingRemainder(dividingBy: 7.8) / 7.8 : 0
            let gaze = sample(p, [(0,0),(0.09,0),(0.15,-1.5),(0.28,-1.5),(0.34,0),(0.40,1.33),(0.53,1.33),(0.60,0),(1,0)])
            let lift = sample(p, [(0,0),(0.09,0),(0.18,-3),(0.27,-3),(0.35,1),(0.43,-5),(0.51,-5),(0.57,2),(0.64,-7),(0.72,1),(0.76,0),(1,0)])
            let tilt = sample(p, [(0,0),(0.09,0),(0.18,-7),(0.27,-7),(0.35,2),(0.43,6),(0.51,6),(0.57,-2),(0.64,0),(1,0)])
            let blink = sample(p, [(0,1),(0.12,1),(0.145,0.12),(0.17,1),(0.31,1),(0.335,0.12),(0.36,1),(0.55,1),(0.575,0.12),(0.60,1),(0.71,1),(0.735,0.12),(0.76,1),(1,1)])
            ZStack {
                SuzentLogoMark(eyeOffset: CGSize(width: gaze, height: animated ? sample(p, [(0,0),(0.15,-0.33),(0.28,-0.33),(0.34,0),(0.40,-0.67),(0.53,-0.67),(0.60,-1),(0.68,-1),(0.76,0),(1,0)]) : 0), blink: blink)
                    .frame(width: 72, height: 72)
                    .rotationEffect(.degrees(tilt), anchor: UnitPoint(x: 0.5, y: 0.8))
                    .offset(y: lift)
                if animated {
                    Rectangle().fill(LinearGradient(colors: [.clear, Color.suzentText.opacity(0.65)], startPoint: .leading, endPoint: .trailing))
                        .frame(width: 44, height: 1)
                        .opacity(sample(p, [(0,0),(0.05,0),(0.12,1),(0.21,0),(1,0)]))
                        .offset(x: -70 + sample(p, [(0,-8),(0.21,13),(1,13)]), y: -10)
                }
            }
        }.frame(width: 210, height: 130)
            .accessibilityElement(children: .ignore).accessibilityLabel("Suzent")
            .onChange(of: active) { _, active in if active { began = Date() } }
            .onChange(of: scenePhase) { _, phase in if phase == .active { began = Date() } }
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

struct AssemblyBadge: View {
    let thinking: Bool
    var parts: [MessagePart] = []
    var streaming = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var started = Date()
    @State private var expanded = false

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !expanded || reduceMotion || scenePhase != .active)) { timeline in
                    Canvas { context, size in
                        context.scaleBy(x: size.width / 320, y: size.height / 108)
                        for mark in AssemblyScene.frame(seconds: timeline.date.timeIntervalSince(started), reduced: reduceMotion) {
                            var path = Path()
                            for (index, point) in mark.points.enumerated() {
                                let position = CGPoint(x: point.x, y: point.y)
                                if index == 0 { path.move(to: position) } else { path.addLine(to: position) }
                            }
                            if mark.points.count > 2 { path.closeSubpath() }
                            let shading = GraphicsContext.Shading.color(Color(presentation: mark.color).opacity(mark.alpha))
                            if mark.stroke { context.stroke(path, with: shading, lineWidth: mark.width) }
                            else { context.fill(path, with: shading) }
                        }
                    }
                }.padding(2).opacity(expanded ? 1 : 0)
                RobotBadge(parts: parts, streaming: streaming).opacity(expanded ? 0 : 1)
            }
            .frame(width: expanded ? min(320, max(90, geometry.size.width - 3)) : 90, height: expanded ? 108 : 40)
            .background(Color.suzentSurface)
            .clipped()
            .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
            .background { Rectangle().fill(Color.suzentShadow).offset(x: PresentationTokens.shadowOffsetOverlay, y: PresentationTokens.shadowOffsetOverlay) }
            .animation(reduceMotion ? nil : .timingCurve(0.22, 1, 0.36, 1, duration: 0.65), value: expanded)
        }
        .frame(height: expanded ? 111 : 43)
        .animation(reduceMotion ? nil : .timingCurve(0.22, 1, 0.36, 1, duration: 0.65), value: expanded)
        .task(id: thinking) {
            if thinking { started = Date() }
            if thinking && !reduceMotion {
                // Let SwiftUI present the default badge before changing the target size.
                try? await Task.sleep(for: .milliseconds(32))
            }
            guard !Task.isCancelled else { return }
            expanded = thinking
        }
        .accessibilityElement(children: .ignore).accessibilityLabel("Suzent")
    }
}

private let robotDrop = Curve(0.175, 0.885, 0.32, 1.275)

/// Desktop's AgentBadge: a robot whose mood follows the turn. It keeps a random personality at rest, dozes off
/// after ten idle seconds, is startled for a moment by each new failure, turns skeptical while approval waits,
/// and wears a face per tool. Every change drops the new face in.
struct RobotBadge: View {
    let parts: [MessagePart]
    let streaming: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var base = robotPersonality(Double.random(in: 0..<1))
    @State private var seenErrors: Int?
    @State private var flash = 0
    @State private var startled = false
    @State private var dropped = Date.distantPast

    private var pending: Bool { parts.contains { $0.type == "tool" && $0.state == "approval-requested" && ($0.output ?? "").isEmpty } }
    private var errors: Int { parts.filter { $0.type == "tool" && toolCallFailed($0) }.count }
    private var variant: RobotVariant {
        robotBadgeVariant(base: base, startled: startled, pending: pending, streaming: streaming, tool: robotCurrentTool(parts))
    }

    private func color(_ role: RobotRole) -> Color {
        switch role {
        case .body: .black
        case .eye: .white
        case .ink: .suzentText
        case .gray: Color(white: 0.4)
        case .dark: Color(white: 0.15)
        }
    }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion || scenePhase != .active)) { timeline in
            let variant = variant
            let drop = reduceMotion ? 1 : min(timeline.date.timeIntervalSince(dropped) / 0.3, 1)
            Canvas { context, size in
                context.scaleBy(x: size.width / RobotScene.slot, y: size.height / RobotScene.slot)
                if RobotScene.clips(variant) { context.clip(to: Path(CGRect(x: 0, y: 0, width: RobotScene.slot, height: RobotScene.slot))) }
                for mark in RobotScene.frame(variant, seconds: timeline.date.timeIntervalSinceReferenceDate, reduced: reduceMotion) {
                    switch mark {
                    case let .shape(points, role, alpha, stroke):
                        var path = Path()
                        for (index, point) in points.enumerated() {
                            if index == 0 { path.move(to: CGPoint(x: point.x, y: point.y)) } else { path.addLine(to: CGPoint(x: point.x, y: point.y)) }
                        }
                        if stroke > 0 { context.stroke(path, with: .color(color(role).opacity(alpha)), style: StrokeStyle(lineWidth: stroke, lineCap: .round)) }
                        else { path.closeSubpath(); context.fill(path, with: .color(color(role).opacity(alpha))) }
                    case let .glyph(text, x, y, size, matrix, role, alpha):
                        var glyph = context
                        glyph.concatenate(CGAffineTransform(a: matrix.a, b: matrix.b, c: matrix.c, d: matrix.d, tx: matrix.e, ty: matrix.f))
                        let resolved = glyph.resolve(Text(text).font(.system(size: size, weight: .bold)).foregroundStyle(color(role).opacity(alpha)))
                        let measured = resolved.measure(in: CGSize(width: CGFloat.infinity, height: .infinity))
                        glyph.draw(resolved, in: CGRect(x: x, y: y - resolved.firstBaseline(in: measured), width: measured.width, height: measured.height))
                    }
                }
            }
            .frame(width: 32, height: 32)
            .scaleEffect(keyframe(drop, [0, 0.5, 1], [0.5, 1.05, 1], robotDrop))
            .offset(y: keyframe(drop, [0, 0.5, 1], [15, -3, 0], robotDrop))
            .opacity(min(max(keyframe(drop, [0, 0.5, 1], [0, 1, 1], robotDrop), 0), 1))
        }
        .onChange(of: errors, initial: true) { _, count in
            if let seen = seenErrors, count > seen { flash += 1 }
            seenErrors = count
        }
        // Keyed on the flash alone: a count that drops when parts reconcile must not cancel the reset and leave it shaking.
        .task(id: flash) {
            guard flash > 0 else { return }
            startled = true
            try? await Task.sleep(for: .milliseconds(2600))
            guard !Task.isCancelled else { return }
            startled = false
        }
        .task(id: "\(streaming):\(pending):\(base.rawValue)") {
            if streaming || pending { if base == .snoozer { base = .idle } }
            else if base == .idle {
                try? await Task.sleep(for: .seconds(10))
                guard !Task.isCancelled else { return }
                base = .snoozer
            }
        }
        .onChange(of: variant) { _, _ in dropped = Date() }
        .accessibilityHidden(true)
    }
}

private struct ChatContentFrameKey: PreferenceKey {
    static var defaultValue: CGRect { .zero }
    static func reduce(value: inout CGRect, nextValue: () -> CGRect) { value = nextValue() }
}

// Scroll measurements drive imperative scrolling, not rendered content. Keeping
// them unobserved avoids rebuilding the message list on every scroll frame.
private final class ChatScrollTracking {
    var following = true
    var dragging = false
    var contentFrame = CGRect.zero
}

private extension View {
    /// Opens at the bottom, but keeps the top fixed when content resizes so a toggled disclosure
    /// grows and shrinks below its header instead of pulling the transcript after it.
    @ViewBuilder func chatScrollAnchor(startsAtBottom: Bool) -> some View {
        if #available(iOS 18, *) {
            defaultScrollAnchor(startsAtBottom ? .bottom : .top, for: .initialOffset)
                .defaultScrollAnchor(.top, for: .sizeChanges)
        } else {
            defaultScrollAnchor(startsAtBottom ? .bottom : .top)
        }
    }
}

struct FollowingChatScrollView<Content: View>: View {
    let openedVersion: Int
    let sentVersion: Int
    let startsAtBottom: Bool
    /// Follow height growth only while a reply streams; a disclosure the user toggles must stay where they tapped.
    var live = false
    let dismissKeyboard: () -> Void
    @ViewBuilder let content: () -> Content
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var tracking = ChatScrollTracking()

    var body: some View {
        GeometryReader { viewport in
            ScrollViewReader { reader in
                ScrollView {
                    content()
                        .background(GeometryReader { geometry in
                            Color.clear.preference(key: ChatContentFrameKey.self,
                                                   value: geometry.frame(in: .named("chat-viewport")))
                        })
                }
                .coordinateSpace(name: "chat-viewport")
                .contentShape(Rectangle())
                .scrollDismissesKeyboard(.interactively)
                .chatScrollAnchor(startsAtBottom: startsAtBottom)
                .simultaneousGesture(TapGesture().onEnded(dismissKeyboard))
                .simultaneousGesture(DragGesture(minimumDistance: 4)
                    .onChanged { _ in
                        tracking.dragging = true
                        tracking.following = false
                    }
                    .onEnded { _ in
                        tracking.dragging = false
                        tracking.following = tracking.contentFrame.maxY <= viewport.size.height + 2
                    })
                .onPreferenceChange(ChatContentFrameKey.self) { frame in
                    let heightChanged = abs(frame.height - tracking.contentFrame.height) > 0.5
                    tracking.contentFrame = frame
                    if !tracking.following && !tracking.dragging && frame.maxY <= viewport.size.height + 2 {
                        tracking.following = true
                    }
                    // Scroll only after layout adds height, never for each received token.
                    if heightChanged && live && tracking.following && !tracking.dragging && startsAtBottom {
                        reader.scrollTo("bottom", anchor: .bottom)
                    }
                }
                .onChange(of: viewport.size.height) { _, _ in
                    if tracking.following && !tracking.dragging && startsAtBottom { reader.scrollTo("bottom", anchor: .bottom) }
                }
                .onChange(of: openedVersion) { _, _ in
                    tracking.following = true
                    reader.scrollTo("bottom", anchor: .bottom)
                }
                .onChange(of: sentVersion) { _, _ in
                    tracking.following = true
                    withAnimation(reduceMotion ? nil : .easeOut(duration: 0.12)) {
                        reader.scrollTo("bottom", anchor: .bottom)
                    }
                }
            }
        }
    }
}
