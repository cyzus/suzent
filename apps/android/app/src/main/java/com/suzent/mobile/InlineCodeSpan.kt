package com.suzent.mobile

import android.graphics.Canvas
import android.graphics.Paint
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.LineBackgroundSpan
import android.widget.TextView
import io.noties.markwon.core.spans.CodeSpan

/**
 * Yellow chip with a black border around each wrapped line of inline code, matching the desktop
 * `box-decoration-clone` rule. Spaces are reserved at both ends so the border does not cover the
 * words beside the code.
 */
fun inlineCodeBordered(source: CharSequence, fill: Int, borderPx: Float, view: TextView): SpannableStringBuilder {
    val text = SpannableStringBuilder(source)
    val spans = text.getSpans(0, text.length, CodeSpan::class.java).sortedByDescending { text.getSpanStart(it) }
    for (span in spans) {
        val start = text.getSpanStart(span)
        val end = text.getSpanEnd(span)
        if (start < 0 || end <= start) continue
        val flags = text.getSpanFlags(span)
        text.insert(end, "\u00A0")
        text.insert(start, "\u00A0")
        text.removeSpan(span)
        text.setSpan(span, start, end + 2, flags)
        text.setSpan(InlineCodeBorderSpan(view, fill, borderPx), start, end + 2, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
    }
    return text
}

private class InlineCodeBorderSpan(private val view: TextView, private val fill: Int, private val borderPx: Float) : LineBackgroundSpan {
    override fun drawBackground(
        canvas: Canvas, paint: Paint, left: Int, right: Int, top: Int, baseline: Int, bottom: Int,
        text: CharSequence, start: Int, end: Int, lineNumber: Int,
    ) {
        val layout = view.layout ?: return
        if (start < 0 || end > layout.text.length || start >= end) return
        val x0 = layout.getPrimaryHorizontal(start)
        val x1 = layout.getPrimaryHorizontal(end.coerceAtMost(layout.text.length))
        val rectLeft = minOf(x0, x1)
        val rectRight = maxOf(x0, x1)
        if (rectRight <= rectLeft) return
        val previousColor = paint.color
        val previousStyle = paint.style
        val previousWidth = paint.strokeWidth
        paint.color = fill
        paint.style = Paint.Style.FILL
        canvas.drawRect(rectLeft, top.toFloat(), rectRight, bottom.toFloat(), paint)
        paint.color = android.graphics.Color.BLACK
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = borderPx
        val inset = borderPx / 2f
        canvas.drawRect(rectLeft + inset, top + inset, rectRight - inset, bottom - inset, paint)
        paint.color = previousColor
        paint.style = previousStyle
        paint.strokeWidth = previousWidth
    }
}
