import Foundation

public enum RenderableMarkdownSection: Equatable, Sendable {
    case markdown(String)
    case spa(String)
}

private let citationPatterns = [
    #"\[\[cite:\s*([^\]\n]+?)\s*\]\]"#,
    "\u{e200}cite\u{e202}([^\u{e201}]+)\u{e201}",
    "\u{fffc}cite\u{fffc}([A-Za-z0-9_,\\s\u{fffc}]+)\u{fffc}",
    #"\bcite[-:]((?:t\d+_src_\d+)(?:\s*,\s*t\d+_src_\d+)*)\b"#,
]

public func markdownWithCitationLinks(_ text: String, sources: [CitationSource]) -> String {
    let byID = Dictionary(uniqueKeysWithValues: sources.map { ($0.id, $0) })
    var result = text
    for pattern in citationPatterns {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { continue }
        let matches = regex.matches(in: result, range: NSRange(result.startIndex..., in: result))
        for match in matches.reversed() {
            guard let whole = Range(match.range, in: result),
                  let payload = Range(match.range(at: 1), in: result) else { continue }
            let ids = result[payload].split(whereSeparator: { $0 == "," || $0 == "\u{e202}" || $0 == "\u{fffc}" })
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
            guard let primary = ids.compactMap({ byID[$0] }).first else {
                result.replaceSubrange(whole, with: "")
                continue
            }
            let suffix = ids.count > 1 ? " +\(ids.count - 1)" : ""
            let label = (primary.title.isEmpty ? primary.id : primary.title).replacingOccurrences(of: "]", with: "\\]") + suffix
            let replacement: String
            if let rawURL = primary.url, let url = URL(string: rawURL), ["http", "https"].contains(url.scheme?.lowercased()) {
                replacement = "[\(label)](<\(rawURL.replacingOccurrences(of: ">", with: "%3E"))>)"
            } else {
                replacement = label
            }
            result.replaceSubrange(whole, with: replacement)
        }
    }
    return result
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
