import Foundation

private let citationPatterns = [
    #"\[\[cite:\s*([^\]\n]+?)\s*\]\]"#,
    "\u{e200}cite\u{e202}([^\u{e201}]+)\u{e201}",
    "\u{fffc}cite\u{fffc}([A-Za-z0-9_,\\s\u{fffc}]+)\u{fffc}",
    #"\bcite[-:]((?:t\d+_src_\d+)(?:\s*,\s*t\d+_src_\d+)*)\b"#,
]

public func markdownWithCitationLinks(_ text: String, sources: [CitationSource], badges: Bool = false) -> String {
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
                let host = url.host?.replacingOccurrences(of: "^www\\.", with: "", options: .regularExpression) ?? primary.title
                let compact = String(host.prefix(26)) + (host.count > 26 ? "…" : "") + suffix
                let badgeLabel = compact.replacingOccurrences(of: "]", with: "\\]")
                let content = badges ? "↗  \(badgeLabel)" : label
                let target = badges ? "suzent-citation://sources/" + ids.map { $0.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "" }.joined(separator: ",") : rawURL.replacingOccurrences(of: ">", with: "%3E")
                replacement = "[\(content)](<\(target)>)"
            } else {
                replacement = label
            }
            result.replaceSubrange(whole, with: replacement)
        }
    }
    return result
}

func citationSourceIDs(_ text: String) -> Set<String> {
    var ids: Set<String> = []
    for pattern in citationPatterns {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { continue }
        for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            guard let payload = Range(match.range(at: 1), in: text) else { continue }
            ids.formUnion(text[payload].split(whereSeparator: { $0 == "," || $0 == "\u{e202}" || $0 == "\u{fffc}" })
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty })
        }
    }
    return ids
}
