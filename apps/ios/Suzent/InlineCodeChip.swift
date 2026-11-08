import SwiftUI
import SuzentCore

/// Words and inline-code chips that wrap together. Each chip is a yellow box with a black border,
/// so a wrapped code span stays one outlined chip instead of a highlight with no edge.
struct InlineCodeParagraph: View {
    let text: String
    var onOpen: (URL) -> Void = { _ in }
    @Environment(\.openURL) private var openURL

    var body: some View {
        let paragraphs = text.components(separatedBy: "\n\n")
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(paragraphs.enumerated()), id: \.offset) { _, paragraph in
                InlineCodeLine(text: paragraph, onOpen: onOpen)
            }
        }
    }
}

private struct InlineCodeLine: View {
    let text: String
    var onOpen: (URL) -> Void

    var body: some View {
        RunLayout(spacing: 0, lineSpacing: 4) {
            ForEach(Array(inlineRuns(text).enumerated()), id: \.offset) { _, run in
                switch run {
                case .word(let word, let strong, let emphasis, let link):
                    let label = Text(word)
                        .fontWeight(strong ? .bold : .regular)
                        .italic(emphasis)
                        .foregroundStyle(link == nil ? Color.suzentText : Color.suzentLink)
                    if let link { label.onTapGesture { onOpen(link) } } else { label }
                case .code(let code):
                    Text(code)
                        .font(.system(size: 13, weight: .semibold, design: .monospaced))
                        .foregroundStyle(.black)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.suzentYellow)
                        .overlay(Rectangle().stroke(Color.black, lineWidth: 2))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

private enum InlineRun {
    case word(String, strong: Bool, emphasis: Bool, link: URL?)
    case code(String)
}

private func inlineRuns(_ text: String) -> [InlineRun] {
    let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
    guard let parsed = try? AttributedString(markdown: text, options: options) else {
        return [.word(text, strong: false, emphasis: false, link: nil)]
    }
    var runs: [InlineRun] = []
    for run in parsed.runs {
        let slice = String(parsed[run.range].characters)
        if run.inlinePresentationIntent?.contains(.code) == true {
            if !slice.isEmpty { runs.append(.code(slice)) }
            continue
        }
        let strong = run.inlinePresentationIntent?.contains(.stronglyEmphasized) == true
        let emphasis = run.inlinePresentationIntent?.contains(.emphasized) == true
        for word in slice.split(separator: " ", omittingEmptySubsequences: false) {
            let shown = word.isEmpty ? " " : String(word) + " "
            if shown == " ", case .word(let previous, let previousStrong, let previousEmphasis, let previousLink) = runs.last,
               previousStrong == strong, previousEmphasis == emphasis, previousLink == run.link {
                runs[runs.count - 1] = .word(previous + " ", strong: strong, emphasis: emphasis, link: run.link)
            } else if !shown.trimmingCharacters(in: .whitespaces).isEmpty || runs.isEmpty {
                runs.append(.word(shown, strong: strong, emphasis: emphasis, link: run.link))
            }
        }
    }
    if case .word(let word, let strong, let emphasis, let link) = runs.last {
        runs[runs.count - 1] = .word(word.replacingOccurrences(of: #" +$"#, with: "", options: .regularExpression), strong: strong, emphasis: emphasis, link: link)
    }
    return runs.filter {
        if case .word(let word, _, _, _) = $0 { return !word.isEmpty }
        return true
    }
}

private struct RunLayout: Layout {
    var spacing: CGFloat = 0
    var lineSpacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(proposal: proposal, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let frames = arrange(proposal: ProposedViewSize(width: bounds.width, height: nil), subviews: subviews).frames
        for (subview, frame) in zip(subviews, frames) {
            subview.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY), proposal: ProposedViewSize(frame.size))
        }
    }

    private func arrange(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, frames: [CGRect]) {
        let limit = proposal.width ?? .greatestFiniteMagnitude
        var frames: [CGRect] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var usedWidth: CGFloat = 0
        for subview in subviews {
            var size = subview.sizeThatFits(ProposedViewSize(width: limit, height: nil))
            if size.width > limit { size.width = limit }
            if x > 0, x + size.width > limit {
                y += rowHeight + lineSpacing
                x = 0
                rowHeight = 0
            }
            frames.append(CGRect(x: x, y: y, width: size.width, height: size.height))
            rowHeight = max(rowHeight, size.height)
            usedWidth = max(usedWidth, x + size.width)
            x += size.width + spacing
        }
        return (CGSize(width: proposal.width ?? usedWidth, height: y + rowHeight), frames)
    }
}
