import Foundation
import Testing
@testable import SuzentCore

@Test func extractsSpaAndHtmlFences() {
    let source = "Before\n\n```spa\n<div id=\"app\"></div>\n```\n\n```HTML title\n<p>Hi</p>\n```\nAfter"
    #expect(renderableMarkdownSections(source) == [
        .markdown("Before\n\n"),
        .spa("<div id=\"app\"></div>\n"),
        .markdown("\n\n"),
        .spa("<p>Hi</p>\n"),
        .markdown("\nAfter"),
    ])
}

@Test func leavesOrdinaryAndIncompleteFencesAsMarkdown() {
    let ordinary = "```swift\nprint(1)\n```"
    let incomplete = "```spa\n<div>streaming"
    #expect(renderableMarkdownSections(ordinary) == [.markdown(ordinary)])
    #expect(renderableMarkdownSections(incomplete) == [.markdown(incomplete)])
}

@Test func turnsCitationMarkersIntoSafeMarkdownLinks() {
    let sources = [CitationSource(id: "t0_src_1", type: "webpage", title: "Example", url: "https://example.com/a", snippet: "A source", favicon: nil)]
    #expect(markdownWithCitationLinks("Fact [[cite:t0_src_1]].", sources: sources) == "Fact [Example](<https://example.com/a>).")
    #expect(markdownWithCitationLinks("Fact \u{e200}cite\u{e202}missing\u{e201}.", sources: sources) == "Fact .")
}

@Test func decodesCitationMetadataForPresentation() throws {
    let data = #"{"type":"citation-sources","citationSources":[{"id":"t0_src_1","type":"webpage","title":"Example","url":"https://example.com","snippet":"A source"}]}"#.data(using: .utf8)!
    let part = try JSONDecoder().decode(MessagePart.self, from: data)
    #expect(part.citationSources?.first?.title == "Example")
}
