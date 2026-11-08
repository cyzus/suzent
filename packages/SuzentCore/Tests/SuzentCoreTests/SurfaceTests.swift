import Foundation
import Testing
@testable import SuzentCore

private struct SurfaceFixtures: Decodable {
    struct Action: Decodable { let name: String; let surface_id: String; let action: String; let context: [String: JSONValue]; let message: String }
    struct QuestionAnswer: Decodable { let context: [String: JSONValue]; let text: String }
    struct DeferredAnswer: Decodable { let context: [String: JSONValue]; let answer: [String: JSONValue] }
    struct CanvasMessage: Decodable { let text: String; let label: String? }
    struct Live: Decodable { let events: [StreamEvent]; let part_types: [String]; let surface_ids: [String]; let latest_text: String }
    struct Chunks: Decodable { let parts: [String]; let kinds: [[String]] }
    let surface: A2UISurface
    let component_types: [String]
    let cell_text: [String: String]
    let actions: [Action]
    let question_answers: [QuestionAnswer]
    let deferred_answers: [DeferredAnswer]
    let canvas_messages: [CanvasMessage]
    let live: Live
    let chunks: Chunks

    static func load() throws -> SurfaceFixtures {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return try JSONDecoder().decode(SurfaceFixtures.self, from: Data(contentsOf: root.appendingPathComponent("mobile-contract/surface-fixtures.json")))
    }
}

@Test func surfaceTreeDecodesEveryComponent() throws {
    let fixtures = try SurfaceFixtures.load()
    #expect(fixtures.surface.component.flattened.map(\.typeName) == fixtures.component_types)
    #expect(!fixtures.surface.isDeferred)
    guard case .card(_, let children) = fixtures.surface.component, case .table(_, let rows) = children[4],
          case .form(let fields, let submit, let action) = children[6] else { Issue.record("unexpected tree"); return }
    #expect(rows[0]["time"]?.displayText == fixtures.cell_text["19:00"])
    #expect(rows[0]["seats"]?.displayText == fixtures.cell_text["2"])
    #expect(rows[1]["seats"]?.displayText == fixtures.cell_text["null"])
    #expect(fields.map(\.kind) == ["text", "number", "select", "multiselect", "checkbox", "textarea"])
    #expect(fields[2].allowFreeText == true && submit == "Save" && action == "notes")
}

@Test func surfaceActionsMatchTheDesktopMessages() throws {
    let fixtures = try SurfaceFixtures.load()
    for action in fixtures.actions {
        #expect(canvasActionMessage(action: action.action, context: action.context, surfaceID: action.surface_id) == action.message, "\(action.name)")
    }
    for item in fixtures.question_answers { #expect(questionAnswerText(item.context) == item.text) }
    for item in fixtures.deferred_answers { #expect(deferredAnswer(item.context) == item.answer) }
    for item in fixtures.canvas_messages { #expect(canvasActionLabel(item.text) == item.label) }
}

@Test func liveSurfacesUpsertAndAnsweredQuestionsLeave() throws {
    let fixtures = try SurfaceFixtures.load()
    var buffer = LiveActivityBuffer()
    fixtures.live.events.forEach { buffer.consume($0) }
    let drained = buffer.drain(); let parts = try #require(drained)
    #expect(parts.map(\.type) == fixtures.live.part_types)
    #expect(parts.compactMap(\.surface?.id) == fixtures.live.surface_ids)
    guard case .text(let content, _, _) = parts.last?.surface?.component else { Issue.record("no surface"); return }
    #expect(content == fixtures.live.latest_text)
}

@Test func surfacesFormTheirOwnChunks() throws {
    let fixtures = try SurfaceFixtures.load()
    let parts = fixtures.chunks.parts.map { MessagePart(type: $0, text: ["text", "reasoning"].contains($0) ? "Answer" : nil, toolCallId: $0 == "tool" ? "t" : nil) }
    #expect(activityChunks(parts).map { $0.map(\.type) } == fixtures.chunks.kinds)
}

@Test func savedSurfacePartsKeepTheirTree() throws {
    let json = #"[{"role":"assistant","content":"","parts":[{"type":"text","text":"Here"},{"type":"a2ui","surface":{"id":"s","component":{"type":"badge","label":"Ok"}}}]}]"#
    let rows = presentMessages(try JSONDecoder().decode([ChatMessage].self, from: Data(json.utf8)))
    #expect(rows.first?.parts.last?.surface?.component == .badge(label: "Ok", color: nil))
}

@Test func malformedSurfacesDegradeWithoutFailingTheMessage() throws {
    let json = #"{"id":"s","component":{"type":"stack","children":[{"type":"badge"},{"type":"divider"}]}}"#
    let surface = try JSONDecoder().decode(A2UISurface.self, from: Data(json.utf8))
    #expect(surface.component.flattened.map(\.typeName) == ["stack", "unknown", "divider"])
    let empty = try JSONDecoder().decode(A2UISurface.self, from: Data(#"{"id":"x"}"#.utf8))
    #expect(empty.component == .unknown(""))
}

@Test func htmlDocumentFitsAPhoneAndSizesToContent() {
    let fragment = surfaceHTMLDocument("<p>Hi</p>")
    #expect(fragment.hasPrefix("<!DOCTYPE html>\n<meta name=\"viewport\""))
    #expect(fragment.contains("body.scrollHeight") && fragment.contains("messageHandlers.surface") && fragment.contains("a2ui:action"))
    let own = surfaceHTMLDocument("<!doctype html><meta name='viewport' content='width=400'><p>Hi</p>")
    #expect(own.hasPrefix("<!doctype html><meta name='viewport'"))
}
