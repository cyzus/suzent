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
