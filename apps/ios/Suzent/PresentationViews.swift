import SwiftUI
import SuzentCore
import MarkdownUI
import SafariServices
import ImageIO

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
    var fallbackModel: String?
    var canRetry = false
    var canEdit = false
    var canFork = false
    var onAction: (String, String?) -> Void = { _, _ in }
    private var user: Bool { message.role == "user" }

    var body: some View {
        VStack(spacing: 10) {
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
                ActivityContent(parts: message.parts, live: false, citationSources: message.citationSources)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
        if ["user", "assistant"].contains(message.role) {
            MessageFooter(message: message, fallbackModel: fallbackModel, canRetry: canRetry, canEdit: canEdit, canFork: canFork, onAction: onAction)
        }
        }
    }
}

private struct MessageFooter: View {
    let message: DisplayMessage
    var fallbackModel: String?
    var canRetry: Bool
    var canEdit: Bool
    var canFork: Bool
    var onAction: (String, String?) -> Void
    @State private var copied = false
    @State private var action: String?
    @State private var edited = ""
    @State private var sourcesOpen = false
    @State private var modelDetails: String?
    private var user: Bool { message.role == "user" }

    var body: some View {
        HStack(spacing: 5) {
                if user { Spacer(minLength: 0) }
                if !message.text.isEmpty {
                    Button {
                        UIPasteboard.general.string = message.text
                        copied = true
                    } label: { Image(systemName: copied ? "checkmark" : "doc.on.doc").frame(width: 32, height: 36) }
                    .accessibilityLabel(copied ? String(localized: "Copied") : String(localized: "Copy message"))
                }
                if canEdit { actionButton("pencil", title: String(localized: "Edit and resend"), action: "edit") }
                if canRetry { actionButton("arrow.clockwise", title: String(localized: "Retry reply"), action: "retry") }
                if canFork { actionButton("arrow.triangle.branch", title: String(localized: "Branch conversation"), action: "fork") }
                if !user && !message.citationSources.isEmpty {
                    Button { sourcesOpen = true } label: {
                        Label("\(message.citationSources.count)", systemImage: "globe")
                            .font(.caption2).lineLimit(1).fixedSize().frame(minHeight: 36)
                    }
                }
                if !user, let model = message.model ?? fallbackModel, !model.isEmpty {
                    Button { modelDetails = model } label: {
                        Text(model.split(separator: "/", maxSplits: 1).last.map(String.init) ?? model)
                            .font(.system(size: 11, weight: .medium)).lineLimit(1).truncationMode(.tail)
                            .padding(.horizontal, 6).padding(.vertical, 3)
                            .frame(maxWidth: 180, alignment: .leading)
                            .overlay(Rectangle().strokeBorder(Color.secondary.opacity(0.3)))
                    }.layoutPriority(-1).accessibilityLabel(model)
                        .accessibilityHint(String(localized: "View full model name"))
                }
                HStack(spacing: 8) {
                    if let raw = message.timestamp {
                        if let date = messageDate(raw) { Text(date, format: .dateTime.day().month(.abbreviated).hour().minute()) }
                        else { Text(raw) }
                    }
                    if user { Text("You") }
                }.font(.system(size: 11)).lineLimit(1).layoutPriority(1)
        }.buttonStyle(.plain).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: user ? .trailing : .leading)
            .alert("Model", isPresented: Binding(get: { modelDetails != nil }, set: { if !$0 { modelDetails = nil } })) {
                Button("Dismiss") { modelDetails = nil }
            } message: { Text(modelDetails ?? "") }
            .task(id: copied) {
                if copied { try? await Task.sleep(for: .seconds(1.8)); copied = false }
            }
            .sheet(isPresented: Binding(get: { action != nil }, set: { if !$0 { action = nil } })) {
                NavigationStack {
                    VStack(alignment: .leading, spacing: 20) {
                        if action == "edit" { TextEditor(text: $edited).frame(minHeight: 140).border(Color.secondary.opacity(0.3)) }
                        else { Text(action == "fork" ? String(localized: "Create a new conversation from this message.") : String(localized: "Replace the latest reply by running the last user message again.")) }
                        Spacer()
                    }.padding(20)
                        .navigationTitle(action == "edit" ? String(localized: "Edit and resend") : action == "fork" ? String(localized: "Branch conversation") : String(localized: "Retry reply"))
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { action = nil } }
                            ToolbarItem(placement: .confirmationAction) { Button("Confirm") {
                                if let action { onAction(action, action == "edit" ? edited : nil) }
                                action = nil
                            }.disabled(action == "edit" && edited.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }
                        }
                }.presentationDetents([.medium, .large])
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
                                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                            }
                        }.padding(20)
                    }.navigationTitle("Sources").navigationBarTitleDisplayMode(.inline)
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Dismiss") { sourcesOpen = false } } }
                }.presentationDetents([.medium, .large])
            }
    }

    private func actionButton(_ icon: String, title: String, action value: String) -> some View {
        Button { edited = message.text; action = value } label: {
            Image(systemName: icon).frame(width: 32, height: 36)
        }.accessibilityLabel(title)
    }

    private func messageDate(_ raw: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}

struct ChatRowButtonStyle: ButtonStyle {
    var selected: Bool
    var destructive = false
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(configuration.isPressed ? (destructive ? Color.white : Color.black) : (destructive ? Color.red : Color.primary))
            .background(configuration.isPressed ? (destructive ? Color.red : Color(presentation: PresentationTokens.yellow)) : selected ? Color.primary.opacity(0.08) : .clear)
            .overlay(alignment: .leading) {
                if selected { Rectangle().fill(Color.primary).frame(width: 3) }
            }
            .opacity(enabled ? 1 : 0.4)
    }
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
        let iconVersions = coordinator.iconURLs.reduce(into: [String: ObjectIdentifier]()) { result, url in
            if let image = icons[url] { result[url] = ObjectIdentifier(image) }
        }
        if coordinator.markdown == markdown, coordinator.sources == sources, coordinator.dark == dark,
           coordinator.iconVersions == iconVersions {
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
        coordinator.selectedURL = selectedURL
        coordinator.badges = [:]
        coordinator.iconURLs = []
        let result = NSMutableAttributedString(parsed)
        let all = NSRange(location: 0, length: result.length)
        let font = UIFont.systemFont(ofSize: CGFloat(PresentationTokens.typeChat))
        result.addAttributes([.font: font, .foregroundColor: UIColor.label], range: all)
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
        view.linkTextAttributes = [.foregroundColor: UIColor.systemBlue]
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
    var softStreaming: Bool? = nil
    @State private var pendingLink: URL?
    @State private var browserLink: URL?
    @StateObject private var icons = CitationIcons()
    @State private var contentCache = CitationContentCache()
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
                                }.font(.caption).foregroundStyle(.secondary)
                                Text(source.title).font(.headline)
                                if !source.snippet.isEmpty { Text(source.snippet).font(.subheadline).lineLimit(6) }
                                Button("Read article") { browserLink = source.url }.buttonStyle(.borderedProminent).clipShape(Capsule())
                                HStack {
                                    Button("Copy link") { UIPasteboard.general.url = source.url }
                                    Spacer()
                                    Button("Open externally") { UIApplication.shared.open(source.url) }
                                }.font(.caption)
                            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
                        }
                    }.padding(24)
                }
                .presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
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
                    } else if let softStreaming, !configuration.content.renderMarkdown().contains("![") {
                        SoftStreamParagraph(markdown: configuration.content.renderMarkdown(), active: softStreaming) { pendingLink = $0 }
                    } else { configuration.label }
                }
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
                .link {
                    ForegroundColor(Color(presentation: PresentationTokens.blue))
                }
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
    var citationSources: [CitationSource] = []
    var body: some View {
        let chunks = activityChunks(parts)
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(chunks.enumerated()), id: \.offset) { index, chunk in
                if chunk.first?.type == "text" { StreamingMarkdown(text: chunk.first?.text ?? "", active: live && index == chunks.count - 1, citationSources: citationSources) }
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

struct AssemblyBadge: View {
    let thinking: Bool
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
                SuzentLogoMark().frame(width: 26, height: 26).opacity(expanded ? 0 : 1)
            }
            .frame(width: expanded ? min(320, max(90, geometry.size.width - 3)) : 90, height: expanded ? 108 : 40)
            .background(Color.suzentSurface)
            .clipped()
            .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
            .background { Rectangle().fill(Color.primary).offset(x: 3, y: 3) }
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

private struct StreamingMarkdown: View {
    let text: String
    let active: Bool
    let citationSources: [CitationSource]
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        SuzentMarkdown(text: streamingMarkdown(text, active: active), citationSources: citationSources,
            softStreaming: active && !reduceMotion)
    }
}

private final class StreamFadeLayoutManager: NSLayoutManager {
    struct Reveal {
        let range: NSRange
        let began: TimeInterval
    }
    var reveals: [Reveal] = []

    override func drawGlyphs(forGlyphRange glyphsToShow: NSRange, at origin: CGPoint) {
        guard let context = UIGraphicsGetCurrentContext(), !reveals.isEmpty else {
            super.drawGlyphs(forGlyphRange: glyphsToShow, at: origin)
            return
        }
        let now = ProcessInfo.processInfo.systemUptime
        let segments = reveals.map { (glyphRange(forCharacterRange: $0.range, actualCharacterRange: nil), $0.began) }
        var boundaries = Set([glyphsToShow.location, NSMaxRange(glyphsToShow)])
        for (range, _) in segments {
            let clipped = NSIntersectionRange(range, glyphsToShow)
            if clipped.length > 0 { boundaries.insert(clipped.location); boundaries.insert(NSMaxRange(clipped)) }
        }
        let sorted = boundaries.sorted()
        for index in 0..<(sorted.count - 1) {
            let range = NSRange(location: sorted[index], length: sorted[index + 1] - sorted[index])
            let began = segments.first { NSLocationInRange(range.location, $0.0) }?.1
            let progress = began.map { min(1, max(0, (now - $0) / 0.15)) } ?? 1
            context.saveGState()
            context.setAlpha(0.12 + 0.88 * (1 - pow(1 - progress, 2)))
            super.drawGlyphs(forGlyphRange: range, at: origin)
            context.restoreGState()
        }
    }
}

private final class StreamFadeTextView: UITextView {
    let fadeLayout: StreamFadeLayoutManager
    private var previous = ""
    private var ticker: Timer?

    init() {
        let storage = NSTextStorage()
        let layout = StreamFadeLayoutManager()
        let container = NSTextContainer(size: .zero)
        container.lineFragmentPadding = 0
        storage.addLayoutManager(layout)
        layout.addTextContainer(container)
        fadeLayout = layout
        super.init(frame: .zero, textContainer: container)
        isScrollEnabled = false
        isEditable = false
        backgroundColor = .clear
        textContainerInset = .zero
        setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }

    func update(_ content: NSAttributedString, active: Bool) {
        let now = ProcessInfo.processInfo.systemUptime
        var body = content.string
        while body.last?.isWhitespace == true { body.removeLast() }
        if body.hasSuffix("▍") { body.removeLast() }
        while body.last?.isWhitespace == true { body.removeLast() }
        if !active || !body.hasPrefix(previous) { fadeLayout.reveals.removeAll() }
        else if body.utf16.count > previous.utf16.count {
            let raw = NSRange(location: previous.utf16.count, length: body.utf16.count - previous.utf16.count)
            let composed = (body as NSString).rangeOfComposedCharacterSequences(for: raw)
            // One fade per received fragment keeps draw calls independent of character count.
            fadeLayout.reveals.append(.init(range: composed, began: now))
        }
        fadeLayout.reveals.removeAll { now - $0.began >= 0.15 || NSMaxRange($0.range) > content.length }
        if !attributedText.isEqual(to: content) { attributedText = content }
        previous = body
        startTicker()
    }

    private func startTicker() {
        guard ticker == nil, window != nil, !fadeLayout.reveals.isEmpty else { return }
        let timer = Timer(timeInterval: 1.0 / 60, repeats: true) { [weak self] timer in
            guard let self else { timer.invalidate(); return }
            MainActor.assumeIsolated {
                let now = ProcessInfo.processInfo.systemUptime
                self.fadeLayout.reveals.removeAll { now - $0.began >= 0.15 }
                self.fadeLayout.invalidateDisplay(forCharacterRange: NSRange(location: 0, length: self.textStorage.length))
                self.setNeedsDisplay()
                if self.fadeLayout.reveals.isEmpty { self.ticker?.invalidate(); self.ticker = nil }
            }
        }
        ticker = timer
        RunLoop.main.add(timer, forMode: .common)
    }
    override func didMoveToWindow() {
        super.didMoveToWindow()
        if window == nil { ticker?.invalidate(); ticker = nil } else { startTicker() }
    }
}

private struct SoftStreamParagraph: UIViewRepresentable {
    let markdown: String
    let active: Bool
    let openLink: (URL) -> Void

    final class Coordinator: NSObject, UITextViewDelegate {
        var openLink: (URL) -> Void
        init(openLink: @escaping (URL) -> Void) { self.openLink = openLink }
        func textView(_ textView: UITextView, shouldInteractWith URL: URL, in characterRange: NSRange, interaction: UITextItemInteraction) -> Bool {
            if ["http", "https", "suzent-citation"].contains(URL.scheme?.lowercased()) { openLink(URL) }
            return false
        }
    }
    func makeCoordinator() -> Coordinator { Coordinator(openLink: openLink) }
    func makeUIView(context: Context) -> StreamFadeTextView {
        let view = StreamFadeTextView()
        view.delegate = context.coordinator
        return view
    }
    func updateUIView(_ view: StreamFadeTextView, context: Context) {
        context.coordinator.openLink = openLink
        let parsed = (try? AttributedString(markdown: markdown, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(markdown)
        let result = NSMutableAttributedString(attributedString: NSAttributedString(parsed))
        let entire = NSRange(location: 0, length: result.length)
        result.addAttributes([.font: UIFont.systemFont(ofSize: PresentationTokens.typeChat), .foregroundColor: UIColor.label], range: entire)
        var offset = 0
        for run in parsed.runs {
            let length = String(parsed[run.range].characters).utf16.count
            let range = NSRange(location: offset, length: length)
            let intent = run.inlinePresentationIntent ?? []
            var font = UIFont.systemFont(ofSize: PresentationTokens.typeChat)
            if intent.contains(.code) {
                font = .monospacedSystemFont(ofSize: PresentationTokens.typeChat, weight: .semibold)
                result.addAttributes([.backgroundColor: UIColor(red: 1, green: 230/255, blue: 102/255, alpha: 1), .foregroundColor: UIColor.black], range: range)
            } else {
                var traits: UIFontDescriptor.SymbolicTraits = []
                if intent.contains(.stronglyEmphasized) { traits.insert(.traitBold) }
                if intent.contains(.emphasized) { traits.insert(.traitItalic) }
                if let descriptor = font.fontDescriptor.withSymbolicTraits(traits) { font = UIFont(descriptor: descriptor, size: PresentationTokens.typeChat) }
            }
            result.addAttribute(.font, value: font, range: range)
            if intent.contains(.strikethrough) { result.addAttribute(.strikethroughStyle, value: NSUnderlineStyle.single.rawValue, range: range) }
            offset += length
        }
        view.linkTextAttributes = [.foregroundColor: UIColor(red: 0, green: 102/255, blue: 1, alpha: 1)]
        view.update(result, active: active)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: StreamFadeTextView, context: Context) -> CGSize? {
        guard let width = proposal.width else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }
}


private struct ChatContentFrameKey: PreferenceKey {
    static var defaultValue: CGRect { .zero }
    static func reduce(value: inout CGRect, nextValue: () -> CGRect) { value = nextValue() }
}

struct FollowingChatScrollView<Content: View>: View {
    let openedVersion: Int
    let sentVersion: Int
    let startsAtBottom: Bool
    let dismissKeyboard: () -> Void
    @ViewBuilder let content: () -> Content
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var following = true
    @State private var dragging = false
    @State private var contentFrame = CGRect.zero

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
                .defaultScrollAnchor(startsAtBottom ? .bottom : .top)
                .simultaneousGesture(TapGesture().onEnded(dismissKeyboard))
                .simultaneousGesture(DragGesture(minimumDistance: 4)
                    .onChanged { _ in
                        dragging = true
                        following = false
                    }
                    .onEnded { _ in
                        dragging = false
                        following = contentFrame.maxY <= viewport.size.height + 2
                    })
                .onPreferenceChange(ChatContentFrameKey.self) { frame in
                    let heightChanged = abs(frame.height - contentFrame.height) > 0.5
                    contentFrame = frame
                    if !following && !dragging && frame.maxY <= viewport.size.height + 2 {
                        following = true
                    }
                    // Scroll only after layout adds height, never for each received token.
                    if heightChanged && following && !dragging && startsAtBottom {
                        withAnimation(reduceMotion ? nil : .easeOut(duration: 0.12)) {
                            reader.scrollTo("bottom", anchor: .bottom)
                        }
                    }
                }
                .onChange(of: viewport.size.height) { _, _ in
                    if following && !dragging && startsAtBottom { reader.scrollTo("bottom", anchor: .bottom) }
                }
                .onChange(of: openedVersion) { _, _ in
                    following = true
                    reader.scrollTo("bottom", anchor: .bottom)
                }
                .onChange(of: sentVersion) { _, _ in
                    following = true
                    withAnimation(reduceMotion ? nil : .easeOut(duration: 0.12)) {
                        reader.scrollTo("bottom", anchor: .bottom)
                    }
                }
            }
        }
    }
}
