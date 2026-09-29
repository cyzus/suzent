import Foundation

public enum RenderableMarkdownSection: Equatable, Sendable {
    case markdown(String)
    case spa(String)
}

/// Splits complete `spa` and `html` fenced blocks from the surrounding Markdown.
/// An unfinished fence remains Markdown so streaming never executes a partial document.
public func renderableMarkdownSections(_ source: String) -> [RenderableMarkdownSection] {
    let pattern = #"^```[ \t]*(?:spa|html)(?:[ \t]+[^\n]*)?\r?\n(.*?)^```[ \t]*$"#
    guard let regex = try? NSRegularExpression(
        pattern: pattern,
        options: [.anchorsMatchLines, .dotMatchesLineSeparators, .caseInsensitive]
    ) else { return [.markdown(source)] }

    let range = NSRange(source.startIndex..<source.endIndex, in: source)
    let matches = regex.matches(in: source, range: range)
    guard !matches.isEmpty else { return source.isEmpty ? [] : [.markdown(source)] }

    var sections: [RenderableMarkdownSection] = []
    var cursor = source.startIndex
    for match in matches {
        guard let whole = Range(match.range, in: source),
              let body = Range(match.range(at: 1), in: source) else { continue }
        if cursor < whole.lowerBound {
            sections.append(.markdown(String(source[cursor..<whole.lowerBound])))
        }
        sections.append(.spa(String(source[body])))
        cursor = whole.upperBound
    }
    if cursor < source.endIndex { sections.append(.markdown(String(source[cursor...]))) }
    return sections
}
