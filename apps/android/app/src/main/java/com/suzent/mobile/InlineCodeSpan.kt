package com.suzent.mobile

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.TextPaint
import android.text.style.LeadingMarginSpan
import android.text.style.MetricAffectingSpan
import android.text.style.ReplacementSpan
import android.widget.TextView
import io.noties.markwon.core.spans.CodeSpan
import java.text.BreakIterator
import kotlin.math.ceil

/** Measures and draws each chip together, including inside indented lists and bold text. */
fun inlineCodeBordered(source: CharSequence, fill: Int, borderPx: Float, view: TextView,
                      availableWidth: Int = view.width): SpannableStringBuilder {
    val text = SpannableStringBuilder(source)
    for (span in text.getSpans(0, text.length, CodeSpan::class.java)) {
        val start = text.getSpanStart(span)
        val end = text.getSpanEnd(span)
        if (start < 0 || end <= start) continue
        val paint = TextPaint(view.paint)
        text.getSpans(start, end, MetricAffectingSpan::class.java)
            .filter { it !== span }.forEach { it.updateMeasureState(paint) }
        span.updateMeasureState(paint)
        text.removeSpan(span)
        val margin = text.getSpans(start, end, LeadingMarginSpan::class.java).sumOf { it.getLeadingMargin(true) }
        val padding = borderPx * 3
        val limit = (availableWidth - margin - padding * 2 - 2).coerceAtLeast(paint.textSize)
        val code = text.subSequence(start, end).toString()
        val boundaries = BreakIterator.getCharacterInstance().apply { setText(code) }
        var chunkStart = 0
        var previous = 0
        var next = boundaries.next()
        // Only oversized code is split, at grapheme boundaries, without changing copied text.
        while (next != BreakIterator.DONE) {
            if (previous > chunkStart && paint.measureText(code, chunkStart, next) > limit) {
                text.setSpan(InlineCodeChip(paint, fill, borderPx), start + chunkStart, start + previous, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                chunkStart = previous
            }
            previous = next
            next = boundaries.next()
        }
        text.setSpan(InlineCodeChip(paint, fill, borderPx), start + chunkStart, end, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
    }
    return text
}

private class InlineCodeChip(private val codePaint: TextPaint, private val fill: Int,
                             private val borderPx: Float) : ReplacementSpan() {
    private val padding = borderPx * 3

    override fun getSize(paint: Paint, text: CharSequence, start: Int, end: Int, fm: Paint.FontMetricsInt?): Int {
        if (fm != null) {
            val metrics = codePaint.fontMetricsInt
            fm.ascent = minOf(fm.ascent, metrics.ascent - ceil(borderPx).toInt())
            fm.descent = maxOf(fm.descent, metrics.descent + ceil(borderPx).toInt())
            fm.top = minOf(fm.top, fm.ascent)
            fm.bottom = maxOf(fm.bottom, fm.descent)
        }
        return ceil(codePaint.measureText(text, start, end) + padding * 2).toInt()
    }

    override fun draw(canvas: Canvas, text: CharSequence, start: Int, end: Int, x: Float,
                      top: Int, y: Int, bottom: Int, paint: Paint) {
        val brush = Paint(codePaint)
        val width = getSize(paint, text, start, end, null)
        val upper = y + codePaint.fontMetrics.ascent - borderPx
        val lower = y + codePaint.fontMetrics.descent + borderPx
        brush.color = fill
        canvas.drawRect(x, upper, x + width, lower, brush)
        brush.color = Color.BLACK
        brush.style = Paint.Style.STROKE
        brush.strokeWidth = borderPx
        val inset = borderPx / 2
        canvas.drawRect(x + inset, upper + inset, x + width - inset, lower - inset, brush)
        brush.style = Paint.Style.FILL
        canvas.drawText(text, start, end, x + padding, y.toFloat(), brush)
    }
}
