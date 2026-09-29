import Foundation
import Testing
@testable import SuzentCore

@Test func turnsCitationMarkersIntoSafeMarkdownLinks() {
    let sources = [CitationSource(id: "t0_src_1", type: "webpage", title: "Example", url: "https://example.com/a", snippet: "A source", favicon: nil)]
    #expect(markdownWithCitationLinks("Fact [[cite:t0_src_1]].", sources: sources) == "Fact [Example](<https://example.com/a>).")
    #expect(markdownWithCitationLinks("Fact [[cite:t0_src_1]].", sources: sources, badges: true) == "Fact [ ↗ example.com ](<https://example.com/a>).")
    #expect(markdownWithCitationLinks("Fact \u{e200}cite\u{e202}t0_src_1\u{e201}.", sources: sources) == "Fact [Example](<https://example.com/a>).")
    #expect(markdownWithCitationLinks("Fact \u{e200}cite\u{e202}missing\u{e201}.", sources: sources) == "Fact .")
}

@Test func decodesCitationMetadataForPresentation() throws {
    let data = #"{"type":"citation-sources","citationSources":[{"id":"t0_src_1","type":"webpage","title":"Example","url":"https://example.com","snippet":"A source"}]}"#.data(using: .utf8)!
    let part = try JSONDecoder().decode(MessagePart.self, from: data)
    #expect(part.citationSources?.first?.title == "Example")
}
