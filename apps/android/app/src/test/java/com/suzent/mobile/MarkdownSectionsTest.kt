package com.suzent.mobile

import org.commonmark.node.BulletList
import org.commonmark.node.Paragraph
import org.commonmark.parser.Parser
import org.junit.Assert.*
import org.junit.Test

class MarkdownSectionsTest {
    private fun sections(text: String) = markdownSections(Parser.builder().build().parse(text))

    @Test fun preservesProseAroundMultipleCodeBlocks() {
        val result = sections("Before\n\n```swift\nlet x = 1\n```\n\nBetween\n\n    indented\n\nAfter")
        assertEquals(5, result.size)
        assertEquals(MarkdownSection.Code("let x = 1", "SWIFT"), result[1])
        assertEquals(MarkdownSection.Code("indented", "CODE"), result[3])
        for (index in listOf(0, 2, 4)) {
            assertTrue((result[index] as MarkdownSection.Prose).document.firstChild is Paragraph)
        }
    }

    @Test fun keepsNestedCodeInsideItsList() {
        val result = sections("- Item\n\n  ```text\n  nested\n  ```")
        assertEquals(1, result.size)
        assertTrue((result.single() as MarkdownSection.Prose).document.firstChild is BulletList)
    }

    @Test fun handlesStreamingUnclosedFenceAndPreservesWhitespace() {
        val result = sections("```python extra\n  value  \n")
        assertEquals(MarkdownSection.Code("  value  ", "PYTHON"), result.single())
        assertTrue(sections("").isEmpty())
    }
}
