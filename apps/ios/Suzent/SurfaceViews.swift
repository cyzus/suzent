import SwiftUI
import WebKit
import SuzentCore

/// An agent-rendered surface inside a reply, with a slim ruled header like the desktop's inline surfaces.
struct SurfaceView: View {
    let surface: A2UISurface
    /// Buttons and forms work; false while they cannot be acted on (no permission, a reply is running, answered).
    let interactive: Bool
    let act: (String, [String: JSONValue]) async -> Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let title = surface.title, !title.isEmpty {
                Text(title.uppercased()).font(.system(size: PresentationTokens.typeSidebarSection, weight: .bold, design: .monospaced))
                    .tracking(1.2).foregroundStyle(Color.suzentMuted).lineLimit(1)
                    .padding(.horizontal, PresentationTokens.spaceMedium).padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Rectangle().fill(Color.suzentOutline).frame(height: PresentationTokens.borderWidth)
            }
            SurfaceComponentView(component: surface.component, interactive: interactive, root: true, act: act)
                .padding(PresentationTokens.spaceMedium)
        }
        .background(Color.suzentSurface)
        .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
    }
}

struct SurfaceComponentView: View {
    let component: A2UIComponent
    let interactive: Bool
    /// The surface's own frame already outlines a top-level card.
    var root = false
    let act: (String, [String: JSONValue]) async -> Bool

    var body: some View {
        switch component {
        case let .text(content, variant, markdown):
            if markdown { SuzentMarkdown(text: content) }
            else { SurfaceText(content: content, variant: variant) }
        case let .badge(label, color): SurfaceBadge(label: label, color: color)
        case let .button(label, action, context, variant, disabled):
            Button(label) {
                var payload = context
                payload["button_label"] = .string(label)
                Task { _ = await act(action, payload) }
            }
            .buttonStyle(SuzentButtonStyle(prominent: variant == nil || variant == "primary", destructive: variant == "danger"))
            .disabled(disabled || !interactive)
        case let .table(columns, rows): SurfaceTable(columns: columns, rows: rows)
        case let .form(fields, submitLabel, action):
            SurfaceForm(fields: fields, submitLabel: submitLabel, interactive: interactive) { await act(action, $0) }
        case let .list(items, ordered):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(ordered ? "\(index + 1)." : "•").monospacedDigit().foregroundStyle(Color.suzentMuted)
                        Text(item).suzentFont(PresentationTokens.typeChat)
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading)
        case let .progress(value, label): SurfaceProgress(value: value, label: label)
        case .divider: Rectangle().fill(Color.suzentRowDivider).frame(height: 1)
        case let .html(html, height): SurfaceHTML(html: html, fixedHeight: height, interactive: interactive, act: act)
        case let .card(title, items):
            VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
                if let title, !title.isEmpty { Text(title).suzentFont(PresentationTokens.typeControl, weight: .bold) }
                children(items)
            }
            .padding(root ? 0 : PresentationTokens.spaceMedium).frame(maxWidth: .infinity, alignment: .leading)
            .overlay(Rectangle().strokeBorder(Color.suzentOutline.opacity(root ? 0 : 0.5), lineWidth: 1))
        case let .columns(items, ratios):
            RatioColumns(ratios: ratios ?? []) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, child in
                    SurfaceComponentView(component: child, interactive: interactive, act: act)
                }
            }
        case let .stack(items, gap):
            VStack(alignment: .leading, spacing: gap == "sm" ? 6 : gap == "lg" ? 20 : PresentationTokens.spaceMedium) { children(items) }
                .frame(maxWidth: .infinity, alignment: .leading)
        case .unknown: EmptyView()
        }
    }

    private func children(_ items: [A2UIComponent]) -> some View {
        ForEach(Array(items.enumerated()), id: \.offset) { _, child in
            SurfaceComponentView(component: child, interactive: interactive, act: act)
        }
    }
}

private struct SurfaceText: View {
    let content: String
    let variant: String?

    var body: some View {
        switch variant {
        case "heading": Text(content).suzentFont(PresentationTokens.typeSection, weight: .bold)
        case "subheading": Text(content).suzentFont(PresentationTokens.typeControl, weight: .semibold)
        case "caption": Text(content).font(.caption).foregroundStyle(Color.suzentMuted)
        case "code":
            ScrollView(.horizontal) {
                Text(content).font(.system(.footnote, design: .monospaced)).textSelection(.enabled).padding(10)
            }.background(Color.suzentCodeBackground)
        default: Text(content).suzentFont(PresentationTokens.typeChat).textSelection(.enabled)
        }
    }
}

private struct SurfaceBadge: View {
    let label: String
    let color: String?

    var body: some View {
        let (fill, ink): (Color, Color) = switch color {
        case "success": (Color(presentation: PresentationTokens.green), .black)
        case "warning": (Color.suzentYellow, .black)
        case "error": (Color.suzentDanger, .white)
        case "info": (Color(presentation: PresentationTokens.blue), .white)
        default: (Color.suzentSelection, Color.suzentText)
        }
        Text(label).font(.caption.weight(.bold)).padding(.horizontal, 8).padding(.vertical, 3)
            .background(fill).foregroundStyle(ink)
            .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: 1))
    }
}

private struct SurfaceProgress: View {
    let value: Double
    let label: String?

    var body: some View {
        let clamped = min(100, max(0, value))
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                if let label { Text(label).font(.subheadline) }
                Spacer()
                Text("\(Int(clamped.rounded()))%").font(.subheadline.monospacedDigit()).foregroundStyle(Color.suzentMuted)
            }
            GeometryReader { proxy in
                Rectangle().fill(Color(presentation: PresentationTokens.blue)).frame(width: proxy.size.width * clamped / 100)
            }
            .frame(height: 10).background(Color.suzentSelection)
            .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(label ?? "")
        .accessibilityValue("\(Int(clamped.rounded()))%")
    }
}

/// Tables scroll sideways rather than squeezing columns to a phone's width.
private struct SurfaceTable: View {
    let columns: [A2UITableColumn]
    let rows: [[String: JSONValue]]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: true) {
            Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
                GridRow {
                    ForEach(columns, id: \.key) { column in
                        cell(column.label).font(.subheadline.weight(.bold)).background(Color.suzentSelection)
                    }
                }
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    GridRow {
                        ForEach(columns, id: \.key) { column in cell(row[column.key]?.displayText ?? "").font(.subheadline) }
                    }
                }
            }
            .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: 1))
        }
    }

    private func cell(_ text: String) -> some View {
        Text(text).textSelection(.enabled).frame(minWidth: 72, maxWidth: 260, alignment: .leading)
            .padding(.horizontal, 10).padding(.vertical, 8)
            .overlay(alignment: .bottom) { Rectangle().fill(Color.suzentRowDivider).frame(height: 1) }
    }
}

/// Side by side when each column gets a usable width, stacked on narrow phones.
private struct RatioColumns: Layout {
    let ratios: [Double]
    private let minimumWidth: CGFloat = 140
    private let spacing: CGFloat = PresentationTokens.spaceMedium

    private func weights(_ count: Int) -> [CGFloat] {
        (0..<count).map { CGFloat($0 < ratios.count && ratios[$0] > 0 ? ratios[$0] : 1) }
    }

    private func widths(_ total: CGFloat, count: Int) -> [CGFloat]? {
        let available = total - spacing * CGFloat(max(0, count - 1))
        let weights = weights(count)
        let sum = weights.reduce(0, +)
        let result = weights.map { available * $0 / sum }
        return result.allSatisfy { $0 >= minimumWidth } ? result : nil
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 320
        if let widths = widths(width, count: subviews.count) {
            let height = zip(subviews, widths).map { $0.sizeThatFits(ProposedViewSize(width: $1, height: nil)).height }.max() ?? 0
            return CGSize(width: width, height: height)
        }
        let heights = subviews.map { $0.sizeThatFits(ProposedViewSize(width: width, height: nil)).height }
        return CGSize(width: width, height: heights.reduce(0, +) + spacing * CGFloat(max(0, subviews.count - 1)))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        if let widths = widths(bounds.width, count: subviews.count) {
            var x = bounds.minX
            for (subview, width) in zip(subviews, widths) {
                subview.place(at: CGPoint(x: x, y: bounds.minY), proposal: ProposedViewSize(width: width, height: nil))
                x += width + spacing
            }
        } else {
            var y = bounds.minY
            for subview in subviews {
                let height = subview.sizeThatFits(ProposedViewSize(width: bounds.width, height: nil)).height
                subview.place(at: CGPoint(x: bounds.minX, y: y), proposal: ProposedViewSize(width: bounds.width, height: nil))
                y += height + spacing
            }
        }
    }
}

private struct SurfaceForm: View {
    let fields: [A2UIFormField]
    let submitLabel: String?
    let interactive: Bool
    let submit: ([String: JSONValue]) async -> Bool
    @State private var values: [String: JSONValue] = [:]
    @State private var otherText: [String: String] = [:]
    @State private var submitted = false

    var body: some View {
        VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
            ForEach(fields, id: \.name) { field in
                VStack(alignment: .leading, spacing: 6) {
                    // A checkbox carries its label on the switch itself.
                    if field.kind != "checkbox" {
                        HStack(spacing: 2) {
                            Text(field.label).font(.subheadline.weight(.semibold))
                            if field.required == true { Text("*").foregroundStyle(Color.suzentDanger).accessibilityHidden(true) }
                        }
                    }
                    input(field)
                }
            }
            Button(submitLabel ?? String(localized: "Submit")) {
                // Locked while sending so a double tap cannot answer twice; a failed send unlocks it to retry.
                submitted = true
                let answer = payload
                Task { if !(await submit(answer)) { submitted = false } }
            }
            .buttonStyle(SuzentButtonStyle(prominent: true))
            .disabled(!interactive || submitted || !complete)
        }
        .disabled(!interactive || submitted)
        .onAppear { if values.isEmpty { values = Dictionary(uniqueKeysWithValues: fields.compactMap { f in f.default.map { (f.name, $0) } }) } }
    }

    /// What the agent receives: each field by name. Typed free text replaces a select's choice and joins a
    /// multiselect's choices, as on the desktop; number fields are converted only now, so editing keeps "1.".
    private var payload: [String: JSONValue] {
        var result = values
        for field in fields {
            let typed = (otherText[field.name] ?? "").trimmingCharacters(in: .whitespaces)
            switch field.kind {
            case "number":
                if case .string(let raw) = values[field.name] {
                    result[field.name] = Double(raw.replacingOccurrences(of: ",", with: ".")).map(JSONValue.number) ?? .string(raw)
                }
            case "multiselect" where !typed.isEmpty:
                result[field.name] = .array(selections(values[field.name]).map(JSONValue.string) + [.string(typed)])
            case "select" where !typed.isEmpty:
                result[field.name] = .string(typed)
            default: break
            }
        }
        for field in fields where result[field.name] == nil {
            switch field.kind {
            case "checkbox": result[field.name] = .bool(false)
            case "multiselect": result[field.name] = .array([])
            default: result[field.name] = .string("")
            }
        }
        return result
    }

    private var complete: Bool {
        fields.filter { $0.required == true }.allSatisfy { field in
            switch payload[field.name] {
            case .string(let text): !text.trimmingCharacters(in: .whitespaces).isEmpty
            case .array(let items): !items.isEmpty
            case .none, .null: false
            default: true
            }
        }
    }

    private func text(_ name: String) -> Binding<String> {
        Binding(get: { values[name]?.displayText ?? "" }, set: { values[name] = .string($0) })
    }

    private func freeText(_ field: A2UIFormField) -> some View {
        TextField(String(localized: "Or type your own"), text: Binding(get: { otherText[field.name] ?? "" }, set: { otherText[field.name] = $0 }))
            .modifier(SurfaceFieldStyle())
    }

    private func selections(_ value: JSONValue?) -> [String] {
        guard case .array(let items) = value else { return [] }
        return items.map(\.displayText)
    }

    @ViewBuilder private func input(_ field: A2UIFormField) -> some View {
        switch field.kind {
        case "number":
            TextField(field.placeholder ?? "", text: text(field.name)).keyboardType(.decimalPad).modifier(SurfaceFieldStyle())
        case "textarea":
            TextField(field.placeholder ?? "", text: text(field.name), axis: .vertical).lineLimit(3...6).modifier(SurfaceFieldStyle())
        case "checkbox":
            Toggle(isOn: Binding(get: { values[field.name] == .bool(true) }, set: { values[field.name] = .bool($0) })) {
                Text(field.label).font(.subheadline.weight(.semibold))
            }.tint(Color(presentation: PresentationTokens.blue))
        case "select":
            VStack(alignment: .leading, spacing: 6) {
                Menu {
                    ForEach(field.options ?? [], id: \.self) { option in
                        Button(option) { values[field.name] = .string(option); otherText[field.name] = nil }
                    }
                } label: {
                    HStack {
                        Text(values[field.name]?.displayText.nilIfEmpty ?? field.placeholder ?? String(localized: "Choose"))
                            .foregroundStyle(values[field.name] == nil ? Color.suzentMuted : Color.suzentText)
                        Spacer()
                        Image(systemName: "chevron.up.chevron.down").font(.caption).foregroundStyle(Color.suzentMuted)
                    }.modifier(SurfaceFieldStyle())
                }
                if field.allowFreeText == true { freeText(field) }
            }
        case "multiselect":
            let chosen = Set(selections(values[field.name]))
            VStack(alignment: .leading, spacing: 6) {
                FlowChips(options: field.options ?? [], chosen: chosen) { option in
                    var next = chosen
                    if next.contains(option) { next.remove(option) } else { next.insert(option) }
                    values[field.name] = .array((field.options ?? []).filter(next.contains).map(JSONValue.string))
                }
                if field.allowFreeText == true { freeText(field) }
            }
        default:
            TextField(field.placeholder ?? "", text: text(field.name)).modifier(SurfaceFieldStyle())
        }
    }
}

private struct SurfaceFieldStyle: ViewModifier {
    func body(content: Content) -> some View {
        content.font(.subheadline).padding(.horizontal, 10).padding(.vertical, 10)
            .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
            .background(Color.suzentBackground)
            .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
    }
}

private struct FlowChips: View {
    let options: [String]
    let chosen: Set<String>
    let toggle: (String) -> Void

    var body: some View {
        WrapLayout(spacing: 8) {
            ForEach(options, id: \.self) { option in
                let on = chosen.contains(option)
                Button { toggle(option) } label: {
                    Text(option).font(.subheadline.weight(on ? .semibold : .regular))
                        .padding(.horizontal, 10).padding(.vertical, 8)
                        .background(on ? Color.suzentYellow : Color.suzentBackground)
                        .foregroundStyle(on ? Color.black : Color.suzentText)
                        .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
    }
}

private struct WrapLayout: Layout {
    let spacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 320
        return CGSize(width: width, height: rows(width, subviews).last.map { $0.y + $0.height } ?? 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for row in rows(bounds.width, subviews) {
            for (index, x) in row.items { subviews[index].place(at: CGPoint(x: bounds.minX + x, y: bounds.minY + row.y), proposal: .unspecified) }
        }
    }

    private func rows(_ width: CGFloat, _ subviews: Subviews) -> [(y: CGFloat, height: CGFloat, items: [(Int, CGFloat)])] {
        var rows: [(y: CGFloat, height: CGFloat, items: [(Int, CGFloat)])] = []
        var x: CGFloat = 0, y: CGFloat = 0, height: CGFloat = 0
        var items: [(Int, CGFloat)] = []
        for (index, subview) in subviews.enumerated() {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > width {
                rows.append((y, height, items)); y += height + spacing; x = 0; height = 0; items = []
            }
            items.append((index, x)); x += size.width + spacing; height = max(height, size.height)
        }
        if !items.isEmpty { rows.append((y, height, items)) }
        return rows
    }
}

/// Agent HTML in an isolated web view: no cookies or storage shared with anything, links open outside the app,
/// and `postMessage({type: 'a2ui:action'})` reaches the agent like a button.
private struct SurfaceHTML: View {
    let html: String
    let fixedHeight: Double?
    let interactive: Bool
    let act: (String, [String: JSONValue]) async -> Bool
    @State private var measured: CGFloat?

    var body: some View {
        // The agent's height is only a first guess until the page reports its content height; a page seen before
        // starts at the height it last measured, so scrolling back to it does not jump.
        HTMLWebView(html: html, interactive: interactive, act: act) { measured = $0 }
            .frame(height: measured ?? SurfacePages.shared.height(html) ?? fixedHeight.map { CGFloat($0) } ?? 120)
            .overlay(Rectangle().strokeBorder(Color.suzentOutline.opacity(0.4), lineWidth: 1))
    }
}

/// Connects a cached page to whichever view is showing it now, and handles its messages and navigation.
private final class SurfaceBridge: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
    let html: String
    var interactive = false
    var act: (String, [String: JSONValue]) async -> Bool = { _, _ in false }
    var resize: (CGFloat) -> Void = { _ in }
    init(html: String) { self.html = html }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let text = message.body as? String,
              let body = try? JSONDecoder().decode([String: JSONValue].self, from: Data(text.utf8)) else { return }
        switch body["kind"]?.text {
        case "height":
            guard case .number(let value) = body["height"] else { return }
            let height = min(max(CGFloat(value), 40), 5000)
            Task { @MainActor in SurfacePages.shared.remember(html, height: height) }
            resize(height)
        case "action":
            guard interactive, let action = body["action"]?.text, !action.isEmpty else { return }
            var context: [String: JSONValue] = [:]
            if case .object(let values) = body["context"] { context = values }
            let act = act
            Task { @MainActor in _ = await act(action, context) }
        default: break
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        // The surface's own document loads in place; anything the user follows opens in the browser.
        if action.navigationType == .linkActivated, let url = action.request.url, ["http", "https", "mailto"].contains(url.scheme ?? "") {
            UIApplication.shared.open(url)
            decisionHandler(.cancel)
        } else if action.targetFrame?.isMainFrame == true, action.navigationType != .other {
            decisionHandler(.cancel)
        } else { decisionHandler(.allow) }
    }
}

/// Loaded pages and their content heights, kept while their reply scrolls off screen. The transcript drops
/// off-screen rows, so without this every return reloaded the page (a blank flash) and re-measured it (a jump).
@MainActor private final class SurfacePages {
    static let shared = SurfacePages()
    private let limit = 4
    private var pages: [(html: String, view: WKWebView, bridge: SurfaceBridge)] = []
    private var heights: [String: CGFloat] = [:]
    private var heightOrder: [String] = []

    func height(_ html: String) -> CGFloat? { heights[html] }

    func remember(_ html: String, height: CGFloat) {
        if heights.updateValue(height, forKey: html) == nil { heightOrder.append(html) }
        if heightOrder.count > 32 { heights[heightOrder.removeFirst()] = nil }
    }

    func obtain(_ html: String) -> (WKWebView, SurfaceBridge) {
        if let index = pages.firstIndex(where: { $0.html == html }) {
            let page = pages.remove(at: index)
            pages.append(page)
            return (page.view, page.bridge)
        }
        let bridge = SurfaceBridge(html: html)
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController.add(bridge, name: "surface")
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = bridge
        view.isOpaque = false
        view.backgroundColor = .clear
        view.scrollView.isScrollEnabled = false
        view.loadHTMLString(surfaceHTMLDocument(html), baseURL: nil)
        pages.append((html, view, bridge))
        // Pages on screen stay; the cache may run over its limit until one scrolls away.
        while pages.count > limit, let index = pages.firstIndex(where: { $0.view.superview == nil && $0.html != html }) {
            let page = pages.remove(at: index)
            page.view.stopLoading()
            page.view.configuration.userContentController.removeScriptMessageHandler(forName: "surface")
        }
        return (view, bridge)
    }
}

private struct HTMLWebView: UIViewRepresentable {
    let html: String
    let interactive: Bool
    let act: (String, [String: JSONValue]) async -> Bool
    let resize: (CGFloat) -> Void

    /// Hosts the cached page, so swapping the page for another surface replaces the subview, not this container.
    func makeUIView(context: Context) -> UIView {
        let container = UIView()
        container.backgroundColor = .clear
        attach(to: container)
        return container
    }

    func updateUIView(_ container: UIView, context: Context) { attach(to: container) }

    private func attach(to container: UIView) {
        let (view, bridge) = SurfacePages.shared.obtain(html)
        bridge.interactive = interactive
        bridge.act = act
        bridge.resize = resize
        guard view.superview !== container else { return }
        container.subviews.forEach { $0.removeFromSuperview() }
        view.frame = container.bounds
        view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        container.addSubview(view)
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
