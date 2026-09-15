package com.suzent.mobile

import org.commonmark.node.Document
import org.commonmark.node.FencedCodeBlock
import org.commonmark.node.IndentedCodeBlock
import org.commonmark.node.Node

internal sealed interface MarkdownSection {
    data class Prose(val document: Document) : MarkdownSection
    data class Code(val text: String, val language: String) : MarkdownSection
}

internal fun markdownSections(document: Node): List<MarkdownSection> {
    val sections = mutableListOf<MarkdownSection>()
    var prose = Document()
    fun flush() {
        if (prose.firstChild != null) sections.add(MarkdownSection.Prose(prose))
        prose = Document()
    }
    var node = document.firstChild
    while (node != null) {
        val next = node.next
        when (val current = node) {
            is FencedCodeBlock -> {
                flush()
                sections.add(MarkdownSection.Code(current.literal.removeSuffix("\n"),
                    current.info.substringBefore(' ').uppercase(java.util.Locale.ROOT).ifEmpty { "CODE" }))
            }
            is IndentedCodeBlock -> {
                flush()
                sections.add(MarkdownSection.Code(current.literal.removeSuffix("\n"), "CODE"))
            }
            else -> prose.appendChild(current)
        }
        node = next
    }
    flush()
    return sections
}
