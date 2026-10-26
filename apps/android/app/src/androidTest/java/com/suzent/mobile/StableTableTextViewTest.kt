package com.suzent.mobile

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.noties.markwon.Markwon
import io.noties.markwon.ext.tables.TablePlugin
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class StableTableTextViewTest {
    private val source = """
        | Item | Description |
        | :--- | ---: |
        | **First** | A wrapped description with enough text to occupy more than one line in a narrow column. |
        | Second | `inline code` and [a link](https://example.com). |
    """.trimIndent()

    @Test fun firstVisibleFrameMatchesTheOriginalSettledTable() = onMain {
        val stable = createStable()
        val reference = createReference()
        bind(stable, source)
        val firstHeight = render(stable, 700).height
        val expected = settledReference(reference, source, 700)
        assertEquals(expected.height, firstHeight)
        assertTrue("Original table appearance changed", expected.sameAs(render(stable, 700)))
    }

    @Test fun streamingUpdatesAndWidthChangesPreserveTheOriginalAppearance() = onMain {
        val stable = createStable()
        val reference = createReference()
        for (width in listOf(700, 1000, 550)) {
            for (text in listOf(source.take(source.lastIndexOf('|')), source, source + "\n| Third | Growing **cell** content with more wrapping text. |")) {
                bind(stable, text)
                val actual = render(stable, width)
                val expected = settledReference(reference, text, width)
                assertEquals("Wrong table height at width $width", expected.height, actual.height)
                assertTrue("Table styling changed during streaming at width $width", expected.sameAs(actual))
            }
        }
    }

    @Test fun darkTableUsesCurrentTextAndLinkColorsOnFirstFrame() = onMain {
        val stable = createStable()
        val reference = createReference()
        for (view in listOf(stable, reference)) {
            view.setTextColor(Color.WHITE)
            view.setLinkTextColor(Color.CYAN)
            view.setBackgroundColor(Color.rgb(24, 24, 24))
        }
        bind(stable, source)
        val actual = render(stable, 700)
        assertTrue("Dark table cached the light theme paint", settledReference(reference, source, 700).sameAs(actual))
    }

    @Test fun themeChangeRefreshesExistingTableLayouts() = onMain {
        val stable = createStable()
        bind(stable, source)
        render(stable, 700)
        stable.setTextColor(Color.WHITE)
        stable.setLinkTextColor(Color.CYAN)
        stable.setBackgroundColor(Color.rgb(24, 24, 24))
        val reference = createReference().apply {
            setTextColor(Color.WHITE)
            setLinkTextColor(Color.CYAN)
            setBackgroundColor(Color.rgb(24, 24, 24))
        }
        assertTrue("Theme change retained cached table colors", settledReference(reference, source, 700).sameAs(render(stable, 700)))
    }

    private fun createStable(): StableTableTextView = StableTableTextView(context()).apply {
        tablePlugin = TablePlugin.create(context())
        configure(this)
    }
    private fun createReference(): TextView = TextView(context()).also(::configure)
    private fun context() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun configure(view: TextView) {
        view.layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        view.textSize = 14f
        view.setTextColor(Color.BLACK)
        view.setBackgroundColor(Color.WHITE)
        view.setLineSpacing(0f, 1.2f)
        view.setTextIsSelectable(true)
    }
    private fun bind(view: TextView, markdown: String) {
        val plugin = if (view is StableTableTextView) requireNotNull(view.tablePlugin) else TablePlugin.create(context())
        val renderer = Markwon.builder(context()).usePlugin(plugin).build()
        val content = renderer.render(renderer.parse(markdown))
        renderer.setParsedMarkdown(view, if (view is StableTableTextView) view.prepareMarkdown(content) else content)
    }
    private fun settledReference(view: TextView, markdown: String, width: Int): Bitmap {
        bind(view, markdown)
        // The original renderer learns its row heights during drawing, then asks
        // TextView to set the text again. Compare against that fully settled image.
        repeat(3) { render(view, width); view.text = view.text }
        return render(view, width)
    }
    private fun render(view: TextView, width: Int): Bitmap {
        view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
        view.layout(0, 0, width, view.measuredHeight)
        return Bitmap.createBitmap(width, view.measuredHeight.coerceAtLeast(1), Bitmap.Config.ARGB_8888).also {
            view.draw(Canvas(it))
        }
    }
    private fun onMain(block: () -> Unit) = InstrumentationRegistry.getInstrumentation().runOnMainSync(block)
}
