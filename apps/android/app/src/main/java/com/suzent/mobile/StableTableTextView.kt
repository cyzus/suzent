package com.suzent.mobile

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Picture
import android.text.SpannableString
import android.text.Spanned
import android.widget.TextView
import io.noties.markwon.core.spans.TextLayoutSpan
import io.noties.markwon.core.spans.TextViewSpan
import io.noties.markwon.ext.tables.TablePlugin
import io.noties.markwon.ext.tables.TableRowSpan

/** Measures the original Markwon rows before the first visible frame, without changing their theme. */
internal class StableTableTextView(context: Context) : TextView(context) {
    var tablePlugin: TablePlugin? = null
    private var preparedRows = emptyList<TableRowSpan>()
    private var preparedWidth = 0
    private var preparedTextSize = 0f
    private var preparedTextColor = 0
    private var preparedLinkColor = 0

    fun prepareMarkdown(content: Spanned): Spanned {
        prepareRows(content, width - compoundPaddingLeft - compoundPaddingRight)
        return content
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val available = MeasureSpec.getSize(widthMeasureSpec) - compoundPaddingLeft - compoundPaddingRight
        if (prepareRows(text, available)) {
            // TextView may already have laid out newly assigned spans using empty row
            // metrics. Rebuild that layout before measuring, not after drawing it.
            text = text
            tablePlugin?.afterSetText(this)
        }
        super.onMeasure(widthMeasureSpec, heightMeasureSpec)
    }

    override fun onDraw(canvas: Canvas) {
        // Color-only changes invalidate drawing without requesting a new measure.
        prepareRows(text, width - compoundPaddingLeft - compoundPaddingRight)
        super.onDraw(canvas)
    }

    private fun prepareRows(content: CharSequence, available: Int): Boolean {
        if (content !is Spanned || available <= 0) return false
        // TextView applies ColorStateList to its paint during onDraw, but table
        // layouts capture that paint here, before the first draw.
        paint.color = currentTextColor
        paint.linkColor = linkTextColors.defaultColor
        val styleChanged = paint.textSize != preparedTextSize ||
            paint.color != preparedTextColor || paint.linkColor != preparedLinkColor
        val rows = content.getSpans(0, content.length, TableRowSpan::class.java).toList()
        if (rows.isEmpty() || rows == preparedRows && available == preparedWidth && !styleChanged) return false
        val measuring = SpannableString(content)
        // The pending text can still refer to the preceding TextView layout. The
        // measurement canvas must supply the upcoming width instead.
        measuring.getSpans(0, measuring.length, TextViewSpan::class.java).forEach(measuring::removeSpan)
        measuring.getSpans(0, measuring.length, TextLayoutSpan::class.java).forEach(measuring::removeSpan)
        val picture = Picture()
        val canvas = picture.beginRecording(available, 1)
        canvas.clipRect(0, 0, 0, 0)
        try {
            for (row in rows) {
                val start = measuring.getSpanStart(row)
                val end = measuring.getSpanEnd(row)
                row.invalidator(null)
                if (row in preparedRows && styleChanged) {
                    val resized = Picture()
                    val resizedCanvas = resized.beginRecording(available + 1, 1)
                    resizedCanvas.clipRect(0, 0, 0, 0)
                    try { row.draw(resizedCanvas, measuring, start, end, 0f, 0, 0, 1, paint) }
                    finally { resized.endRecording() }
                }
                row.draw(canvas, measuring, start, end, 0f, 0, 0, 1, paint)
                row.getSize(paint, measuring, start, end, Paint.FontMetricsInt())
            }
        } finally { picture.endRecording() }
        preparedRows = rows
        preparedWidth = available
        preparedTextSize = paint.textSize
        preparedTextColor = paint.color
        preparedLinkColor = paint.linkColor
        return true
    }
}
