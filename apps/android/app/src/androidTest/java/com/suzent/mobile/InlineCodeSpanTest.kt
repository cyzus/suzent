package com.suzent.mobile

import android.graphics.Color
import android.text.Spanned
import android.text.style.ReplacementSpan
import android.view.View
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.noties.markwon.Markwon
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class InlineCodeSpanTest {
    @Test fun shortCodeMovesToNextLineAsOneChip() {
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val context = InstrumentationRegistry.getInstrumentation().targetContext
            val view = TextView(context).apply { textSize = 16f }
            val renderer = Markwon.create(context)
            renderer.setMarkdown(view, "前面的文字 `3m ago`、`10m ago`")
            val width = view.paint.measureText("前面的文字 3m").toInt()
            view.text = inlineCodeBordered(view.text, Color.YELLOW, 2f, view, width)
            val text = view.text as Spanned
            view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
            view.layout(0, 0, width, view.measuredHeight)
            val chips = text.getSpans(0, text.length, ReplacementSpan::class.java)
            assertEquals(2, chips.size)
            for (chip in chips) {
                assertEquals(view.layout.getLineForOffset(text.getSpanStart(chip)),
                    view.layout.getLineForOffset(text.getSpanEnd(chip) - 1))
            }
            assertTrue(view.layout.lineCount > 1)
        }
    }

    @Test fun longCodeStillWrapsWithinNarrowParagraph() {
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val context = InstrumentationRegistry.getInstrumentation().targetContext
            val view = TextView(context).apply { textSize = 16f }
            Markwon.create(context).setMarkdown(view, "`very_long_command_with_arguments --another-option value`")
            val width = 220
            view.text = inlineCodeBordered(view.text, Color.YELLOW, 2f, view, width)
            view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
            view.layout(0, 0, width, view.measuredHeight)
            assertTrue(view.layout.lineCount > 1)
            for (line in 0 until view.layout.lineCount) assertTrue(view.layout.getLineRight(line) <= width + 1)
        }
    }
    @Test fun nestedBoldCodePreservesTextAndFitsAfterResize() {
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val context = InstrumentationRegistry.getInstrumentation().targetContext
            val view = StableTableTextView(context).apply {
                layoutParams = android.view.ViewGroup.LayoutParams(-1, -2)
                textSize = 16f
                setTextColor(Color.WHITE)
                setBackgroundColor(Color.rgb(24, 24, 24))
                setLineSpacing(0f, 1.2f)
            }
            val markdown = """
                1. **`Inbox` 与 `Rules` 彻底分离：**
                   - **`Inbox` 页面**：移除了每一行右侧的 `<BrutalSelect />` 下拉框，统一改为只读去向标签（`→ Regent`、`→ [项目]` 或 `Unrouted`），点击标签直接跳进对应会话。
                   - **`Rules` 页面**：作为唯一带 **`<BrutalSelect />` 下拉框的规则控制台**，专门管理每种事件签名未来的路由去向。
                2. 初始规则生成去硬编码化：
                   - 拿掉了之前写死的 `workflow_run.success` 等硬编码过滤表（仅保留 `ping` 连通性握手不唤醒模型）。
                   - 长命令：`very_long_command_with_arguments --another-option value`。
            """.trimIndent()
            Markwon.create(context).setMarkdown(view, markdown)
            val original = view.text.toString()
            view.setInlineCode(view.text, Color.YELLOW, 2f)
            for (width in listOf(700, 440, 900)) {
                view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                view.layout(0, 0, width, view.measuredHeight)
                assertEquals(original, view.text.toString())
                val styled = view.text as Spanned
                for (chip in styled.getSpans(0, styled.length, ReplacementSpan::class.java)) {
                    val start = styled.getSpanStart(chip)
                    val end = styled.getSpanEnd(chip)
                    assertEquals(view.layout.getLineForOffset(start), view.layout.getLineForOffset(end - 1))
                    assertTrue("Code chip exceeds paragraph width", chip.getSize(view.paint, styled, start, end, null) <= width)
                }
                // CJK closing punctuation can hang beyond the paragraph edge by one glyph.
                for (line in 0 until view.layout.lineCount) assertTrue(view.layout.getLineRight(line) <= width + view.paint.textSize)

            }
        }
    }

}
