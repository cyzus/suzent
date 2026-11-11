import Foundation
import Testing
@testable import SuzentCore

@Test func turnsCitationMarkersIntoSafeMarkdownLinks() {
    let sources = [CitationSource(id: "t0_src_1", type: "webpage", title: "Example", url: "https://example.com/a", snippet: "A source", favicon: nil)]
    #expect(markdownWithCitationLinks("Fact [[cite:t0_src_1]].", sources: sources) == "Fact [Example](<https://example.com/a>).")
    #expect(markdownWithCitationLinks("Fact [[cite:t0_src_1]].", sources: sources, badges: true) == "Fact [↗  example.com](<suzent-citation://sources/t0%5Fsrc%5F1#badge-0>).")
    let repeated = markdownWithCitationLinks("[[cite:t0_src_1]] and \u{e200}cite\u{e202}t0_src_1\u{e201}", sources: sources, badges: true)
    #expect(repeated.contains("#badge-0"))
    #expect(repeated.contains("#badge-1"))
    #expect(markdownWithCitationLinks("Fact \u{e200}cite\u{e202}t0_src_1\u{e201}.", sources: sources) == "Fact [Example](<https://example.com/a>).")
    #expect(markdownWithCitationLinks("Fact \u{e200}cite\u{e202}missing\u{e201}.", sources: sources) == "Fact .")
}

@Test func inlineCodeParagraphsSplitAwayFromFences() {
    let pieces = markdownPieces("Run `git status` now.\n\n```swift\nkeep `this`\n```\n\n- item `code`")
    #expect(pieces.contains(.inline("Run `git status` now.")))
    #expect(pieces.contains { if case .markdown(let text) = $0 { return text.contains("keep `this`") } else { return false } })
    #expect(pieces.contains { if case .inline(let text) = $0 { return text.contains("- item `code`") } else { return false } })
    #expect(markdownPieces("A lone ` stays.") == [.markdown("A lone ` stays.")])
    #expect(markdownPieces("# Title `code`") == [.markdown("# Title `code`")])
}

@Test func decodesCitationMetadataForPresentation() throws {
    let data = #"{"type":"citation-sources","citationSources":[{"id":"t0_src_1","type":"webpage","title":"Example","url":"https://example.com","snippet":"A source"}]}"#.data(using: .utf8)!
    let part = try JSONDecoder().decode(MessagePart.self, from: data)
    #expect(part.citationSources?.first?.title == "Example")
}

@Test func citationsFollowSharedFixtures() throws {
    struct Fixtures: Decodable {
        struct Case: Decodable {
            let name: String
            let text: String
            let cites: [[String]]
            let keeps: [String]
            let drops: [String]
        }
        let sources: [CitationSource]
        let cases: [Case]
    }
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("mobile-contract/citation-fixtures.json"))
    let fixtures = try JSONDecoder().decode(Fixtures.self, from: data)
    let link = try NSRegularExpression(pattern: "suzent-citation://sources/([^#>]+)#")
    for fixture in fixtures.cases {
        let output = markdownWithCitationLinks(fixture.text, sources: fixtures.sources, badges: true)
        let cites = link.matches(in: output, range: NSRange(output.startIndex..., in: output)).compactMap { match in
            Range(match.range(at: 1), in: output).map { output[$0].split(separator: ",").map { $0.removingPercentEncoding ?? String($0) } }
        }
        let key = { (ids: [String]) in ids.joined(separator: ",") }
        #expect(cites.sorted { key($0) < key($1) } == fixture.cites.sorted { key($0) < key($1) }, "\(fixture.name): \(output)")
        for kept in fixture.keeps { #expect(output.contains(kept), "\(fixture.name) keeps \(kept): \(output)") }
        for dropped in fixture.drops { #expect(!output.contains(dropped), "\(fixture.name) drops \(dropped): \(output)") }
    }
}
