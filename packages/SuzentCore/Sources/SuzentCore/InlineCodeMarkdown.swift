import Foundation

public enum MarkdownPiece: Equatable, Sendable {
    /// A fence or a block MarkdownUI should render (lists, tables, headings).
    case markdown(String)
    /// A paragraph that contains inline code and no other block structure.
    case inline(String)
}

/// Splits a document so inline ``code`` can be drawn as bordered chips without
/// sending fenced blocks or lists through that path.
public func markdownPieces(_ markdown: String) -> [MarkdownPiece] {
    let chars = Array(markdown)
    var index = 0
    var pieces: [MarkdownPiece] = []
    var prose = ""
    func flush() {
        let trimmed = prose
        prose = ""
        guard !trimmed.isEmpty else { return }
        if trimmed.allSatisfy({ $0 == "\n" }) { return }
        pieces.append(prosePiece(trimmed))
    }
    while index < chars.count {
        if lineStart(chars, index), let fence = fenceRun(chars, index), fence.length >= 3,
           let end = closingFence(chars, from: fence.content, marker: fence.marker, length: fence.length) {
            flush()
            pieces.append(.markdown(String(chars[index..<end])))
            index = end
            continue
        }
        prose.append(chars[index])
        index += 1
    }
    flush()
    return pieces
}

private func prosePiece(_ text: String) -> MarkdownPiece {
    let body = text.trimmingCharacters(in: .newlines)
    guard hasInlineCode(body), !hasBlockStructure(body) else { return .markdown(text) }
    return .inline(body)
}

private func hasInlineCode(_ text: String) -> Bool {
    let chars = Array(text)
    var index = 0
    while index < chars.count {
        if chars[index] == "`" {
            let opener = backtickRun(chars, index)
            if matchingRun(chars, from: opener.end, length: opener.length) != nil { return true }
            index = opener.end
        } else {
            index += 1
        }
    }
    return false
}

private func hasBlockStructure(_ text: String) -> Bool {
    for line in text.split(separator: "\n", omittingEmptySubsequences: false) {
        let trimmed = line.drop(while: { $0 == " " })
        // Lists stay in this path: the marker is ordinary text and the code can keep its border.
        // Headings, quotes and tables stay with MarkdownUI.
        if trimmed.hasPrefix("#") || trimmed.hasPrefix(">") || trimmed.hasPrefix("|") {
            return true
        }
    }
    return false
}

private func lineStart(_ chars: [Character], _ index: Int) -> Bool {
    index == 0 || chars[index - 1] == "\n"
}

private struct FenceRun {
    let marker: Character
    let length: Int
    let content: Int
}

private func fenceRun(_ chars: [Character], _ index: Int) -> FenceRun? {
    var cursor = index
    var spaces = 0
    while cursor < chars.count, spaces < 4, chars[cursor] == " " {
        cursor += 1
        spaces += 1
    }
    guard cursor < chars.count, chars[cursor] == "`" || chars[cursor] == "~" else { return nil }
    let marker = chars[cursor]
    let start = cursor
    while cursor < chars.count, chars[cursor] == marker { cursor += 1 }
    return FenceRun(marker: marker, length: cursor - start, content: cursor)
}

private func closingFence(_ chars: [Character], from: Int, marker: Character, length: Int) -> Int? {
    var cursor = from
    while cursor < chars.count, chars[cursor] != "\n" { cursor += 1 }
    if cursor < chars.count { cursor += 1 }
    while cursor < chars.count {
        if lineStart(chars, cursor), let run = fenceRun(chars, cursor), run.marker == marker, run.length >= length {
            var end = run.content
            while end < chars.count, chars[end] == " " { end += 1 }
            if end == chars.count || chars[end] == "\n" { return end < chars.count ? end + 1 : end }
        }
        cursor += 1
    }
    return nil
}

private func backtickRun(_ chars: [Character], _ index: Int) -> (length: Int, end: Int) {
    var cursor = index
    while cursor < chars.count, chars[cursor] == "`" { cursor += 1 }
    return (cursor - index, cursor)
}

private func matchingRun(_ chars: [Character], from: Int, length: Int) -> Int? {
    var cursor = from
    while cursor < chars.count {
        if chars[cursor] == "`" {
            let run = backtickRun(chars, cursor)
            if run.length == length { return cursor }
            cursor = run.end
        } else {
            cursor += 1
        }
    }
    return nil
}
