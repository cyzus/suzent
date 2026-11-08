import Foundation

/// An agent-rendered surface (desktop A2UI): a component tree shown in the chat.
public struct A2UISurface: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let title: String?
    public let component: A2UIComponent
    public let target: String?
    public let rev: Double?
    /// Rendered by ask_question: the agent waits for the answer instead of a new message.
    public let deferred: Bool?

    public var isDeferred: Bool { deferred == true }

    private enum Keys: String, CodingKey { case id, title, component, target, rev, deferred }

    /// A malformed surface degrades to an empty one instead of failing the message that carries it.
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? ""
        title = try? c.decodeIfPresent(String.self, forKey: .title)
        component = (try? c.decode(A2UIComponent.self, forKey: .component)) ?? .unknown("")
        target = try? c.decodeIfPresent(String.self, forKey: .target)
        rev = try? c.decodeIfPresent(Double.self, forKey: .rev)
        deferred = try? c.decodeIfPresent(Bool.self, forKey: .deferred)
    }
}

/// Decodes one child, keeping its siblings when it is malformed.
private struct LossyComponent: Decodable {
    let value: A2UIComponent
    init(from decoder: Decoder) throws { value = (try? A2UIComponent(from: decoder)) ?? .unknown("") }
}

public struct A2UITableColumn: Decodable, Sendable, Equatable {
    public let key: String
    public let label: String
}

public struct A2UIFormField: Decodable, Sendable, Equatable {
    public let name: String
    public let label: String
    public let type: String?
    public let options: [String]?
    public let allowFreeText: Bool?
    public let required: Bool?
    public let `default`: JSONValue?
    public let placeholder: String?

    enum CodingKeys: String, CodingKey {
        case name, label, type, options, required, placeholder, `default`
        case allowFreeText = "allow_free_text"
    }

    public var kind: String { type ?? "text" }
}

public indirect enum A2UIComponent: Decodable, Sendable, Equatable {
    case text(content: String, variant: String?, markdown: Bool)
    case badge(label: String, color: String?)
    case button(label: String, action: String, context: [String: JSONValue], variant: String?, disabled: Bool)
    case table(columns: [A2UITableColumn], rows: [[String: JSONValue]])
    case form(fields: [A2UIFormField], submitLabel: String?, action: String)
    case list(items: [String], ordered: Bool)
    case progress(value: Double, label: String?)
    case divider
    case html(html: String, height: Double?)
    case card(title: String?, children: [A2UIComponent])
    case columns(children: [A2UIComponent], ratios: [Double]?)
    case stack(children: [A2UIComponent], gap: String?)
    /// A component this app version does not know; it renders nothing rather than failing the whole surface.
    case unknown(String)

    private enum Keys: String, CodingKey {
        case type, content, variant, markdown, label, color, action, context, disabled, columns, rows
        case fields, items, ordered, value, html, height, title, children, ratios, gap
        case submitLabel = "submit_label"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        let type = try c.decode(String.self, forKey: .type)
        func children() throws -> [A2UIComponent] { (try c.decodeIfPresent([LossyComponent].self, forKey: .children) ?? []).map(\.value) }
        switch type {
        case "text":
            self = .text(content: try c.decodeIfPresent(String.self, forKey: .content) ?? "",
                         variant: try c.decodeIfPresent(String.self, forKey: .variant),
                         markdown: try c.decodeIfPresent(Bool.self, forKey: .markdown) ?? false)
        case "badge": self = .badge(label: try c.decode(String.self, forKey: .label), color: try c.decodeIfPresent(String.self, forKey: .color))
        case "button":
            self = .button(label: try c.decode(String.self, forKey: .label), action: try c.decode(String.self, forKey: .action),
                           context: try c.decodeIfPresent([String: JSONValue].self, forKey: .context) ?? [:],
                           variant: try c.decodeIfPresent(String.self, forKey: .variant),
                           disabled: try c.decodeIfPresent(Bool.self, forKey: .disabled) ?? false)
        case "table":
            self = .table(columns: try c.decodeIfPresent([A2UITableColumn].self, forKey: .columns) ?? [],
                          rows: try c.decodeIfPresent([[String: JSONValue]].self, forKey: .rows) ?? [])
        case "form":
            self = .form(fields: try c.decodeIfPresent([A2UIFormField].self, forKey: .fields) ?? [],
                         submitLabel: try c.decodeIfPresent(String.self, forKey: .submitLabel),
                         action: try c.decodeIfPresent(String.self, forKey: .action) ?? "submit")
        case "list": self = .list(items: try c.decodeIfPresent([String].self, forKey: .items) ?? [], ordered: try c.decodeIfPresent(Bool.self, forKey: .ordered) ?? false)
        case "progress": self = .progress(value: try c.decodeIfPresent(Double.self, forKey: .value) ?? 0, label: try c.decodeIfPresent(String.self, forKey: .label))
        case "divider": self = .divider
        case "html": self = .html(html: try c.decodeIfPresent(String.self, forKey: .html) ?? "", height: try c.decodeIfPresent(Double.self, forKey: .height))
        case "card": self = .card(title: try c.decodeIfPresent(String.self, forKey: .title), children: try children())
        case "columns": self = .columns(children: try children(), ratios: try c.decodeIfPresent([Double].self, forKey: .ratios))
        case "stack": self = .stack(children: try children(), gap: try c.decodeIfPresent(String.self, forKey: .gap))
        default: self = .unknown(type)
        }
    }

    public var typeName: String {
        switch self {
        case .text: "text"
        case .badge: "badge"
        case .button: "button"
        case .table: "table"
        case .form: "form"
        case .list: "list"
        case .progress: "progress"
        case .divider: "divider"
        case .html: "html"
        case .card: "card"
        case .columns: "columns"
        case .stack: "stack"
        case .unknown: "unknown"
        }
    }

    /// Every component in the tree, depth first, this one included.
    public var flattened: [A2UIComponent] {
        switch self {
        case .card(_, let children), .columns(let children, _), .stack(let children, _): [self] + children.flatMap(\.flattened)
        default: [self]
        }
    }
}

extension JSONValue: Equatable {
    public static func == (lhs: JSONValue, rhs: JSONValue) -> Bool {
        switch (lhs, rhs) {
        case let (.string(a), .string(b)): a == b
        case let (.number(a), .number(b)): a == b
        case let (.bool(a), .bool(b)): a == b
        case let (.object(a), .object(b)): a == b
        case let (.array(a), .array(b)): a == b
        case (.null, .null): true
        default: false
        }
    }

    /// How a value reads in a table cell or a question answer.
    public var displayText: String {
        switch self {
        case .string(let value): value
        case .number(let value): value.rounded() == value && abs(value) < 1e15 ? String(Int64(value)) : String(value)
        case .bool(let value): value ? "true" : "false"
        case .null: ""
        case .array(let values): values.map(\.displayText).joined(separator: ", ")
        case .object: (try? String(data: JSONEncoder().encode(self), encoding: .utf8)) ?? ""
        }
    }

    var foundationValue: Any {
        switch self {
        case .string(let value): value
        case .number(let value): value.rounded() == value && abs(value) < 1e15 ? Int64(value) as Any : value
        case .bool(let value): value
        case .null: NSNull()
        case .array(let values): values.map(\.foundationValue)
        case .object(let values): values.mapValues(\.foundationValue)
        }
    }
}

/// What the agent reads when a button or form on an ordinary surface is used: the desktop's canvas message.
public func canvasActionMessage(action: String, context: [String: JSONValue], surfaceID: String) -> String {
    var rest = context
    let label = rest.removeValue(forKey: "button_label")?.displayText
    if !surfaceID.isEmpty, rest["surface_id"] == nil { rest["surface_id"] = .string(surfaceID) }
    var message = "[canvas: \(action)]"
    if let label, !label.isEmpty { message += " \"\(label)\"" }
    if !rest.isEmpty { message += " " + compactJSON(rest) }
    return message
}

/// A question form that did not hold the turn open is answered as the user's next message.
public func questionAnswerText(_ context: [String: JSONValue]) -> String {
    if let label = context["button_label"]?.displayText.trimmingCharacters(in: .whitespacesAndNewlines), !label.isEmpty { return label }
    return context.filter { $0.key != "button_label" && $0.key != "surface_id" }
        .sorted { $0.key < $1.key }
        .map { "\($0.key): \($0.value.displayText.trimmingCharacters(in: .whitespacesAndNewlines))" }
        .joined(separator: "\n")
}

/// What a blocked ask_question receives: the form values, or the pressed button's label as `answer`.
public func deferredAnswer(_ context: [String: JSONValue]) -> [String: JSONValue] {
    var answer = context
    if let label = answer.removeValue(forKey: "button_label") { answer["answer"] = label }
    return answer
}

/// The label of a user message that came from a surface action, or nil for an ordinary message.
public func canvasActionLabel(_ text: String) -> String? {
    guard let match = text.firstMatch(of: /^\[canvas: ([^\]]+)\](?: "([^"]*)")?/) else { return nil }
    if let label = match.2, !label.isEmpty { return String(label) }
    return String(match.1)
}

public func compactJSON(_ value: [String: JSONValue]) -> String {
    let object = value.mapValues(\.foundationValue)
    guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes]) else { return "{}" }
    return String(data: data, encoding: .utf8) ?? "{}"
}

extension JSONValue {
    /// A surface carried inside a stream event or a message part.
    func decodeSurface() -> A2UISurface? {
        guard let data = try? JSONEncoder().encode(self) else { return nil }
        return try? JSONDecoder().decode(A2UISurface.self, from: data)
    }
}

/// Agent HTML written for a desktop iframe, made to fit a phone reply: a phone viewport, standards mode, and the
/// desktop's auto-size shim. It reports `{kind: "height"}` as content grows (fonts, images, script output) and
/// forwards `postMessage({type: "a2ui:action"})` as `{kind: "action"}`. Phones always size to content: a fixed
/// height would need scrolling inside the page, which the chat's own scroll takes over.
public func surfaceHTMLDocument(_ html: String) -> String {
    var document = html
    if document.range(of: #"<meta[^>]+name=["']?viewport"#, options: [.regularExpression, .caseInsensitive]) == nil {
        document = #"<meta name="viewport" content="width=device-width, initial-scale=1">"# + document
    }
    if document.range(of: #"^\s*<!doctype\s"#, options: [.regularExpression, .caseInsensitive]) == nil {
        document = "<!DOCTYPE html>\n" + document
    }
    return document + "\n" + surfaceHTMLShim
}

let surfaceHTMLShim = #"""
<style>html, body { height: auto !important; min-height: 0 !important; }</style>
<script>
(function () {
  function post(body) {
    var text = JSON.stringify(body);
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.surface) window.webkit.messageHandlers.surface.postMessage(text);
    else if (window.SuzentSurface) window.SuzentSurface.post(text);
  }
  window.addEventListener('message', function (event) {
    var data = event.data;
    if (data && data.type === 'a2ui:action' && typeof data.action === 'string') post({ kind: 'action', action: data.action, context: data.context || {} });
  });
  var pending = false;
  var previous = 0;
  function measure() {
    pending = false;
    var body = document.body;
    if (!body || !document.documentElement.clientWidth) return;
    var style = getComputedStyle(body);
    var height = Math.ceil(Math.max(body.scrollHeight, body.getBoundingClientRect().height) + (parseFloat(style.marginTop) || 0) + (parseFloat(style.marginBottom) || 0));
    if (height > 0 && height !== previous) { previous = height; post({ kind: 'height', height: height }); }
  }
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(measure);
  }
  window.addEventListener('load', schedule);
  window.addEventListener('resize', schedule);
  document.addEventListener('load', schedule, true);
  if (window.ResizeObserver) {
    var observer = new ResizeObserver(schedule);
    observer.observe(document.documentElement);
    observer.observe(document.body);
  }
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
  if (document.fonts) document.fonts.ready.then(schedule);
  schedule();
})();
</script>
"""#
