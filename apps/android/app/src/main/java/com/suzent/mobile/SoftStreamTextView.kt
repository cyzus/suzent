package com.suzent.mobile

import android.content.Context
import android.icu.text.BreakIterator
import android.graphics.Canvas
import android.os.SystemClock
import android.text.SpannableString
import android.text.Spanned
import android.text.TextPaint
import android.text.style.CharacterStyle
import android.widget.TextView

/** Fades only appended glyphs; animation frames never parse or lay out Markdown. */
class SoftStreamTextView(context: Context) : TextView(context) {
    private data class Reveal(val start: Int, val end: Int, val began: Long)
    private var previous = ""
    private var reveals = mutableListOf<Reveal>()

    fun prepare(styled: SpannableString, active: Boolean): SpannableString {
        val now = SystemClock.uptimeMillis()
        val body = styled.toString().trimEnd().removeSuffix("▍").trimEnd()
        if (!active || !body.startsWith(previous)) reveals.clear()
        else if (body.length > previous.length) {
            val boundaries = BreakIterator.getCharacterInstance().apply { setText(body) }
            var start = previous.length
            if (!boundaries.isBoundary(start)) start = boundaries.preceding(start)
            // One fade per received fragment avoids per-character spans and delayed invisible ink.
            reveals += Reveal(start, body.length, now)
        }
        reveals.removeAll { now - it.began >= 150 || it.end > styled.length }
        if (active) reveals.forEach { reveal ->
            styled.setSpan(object : CharacterStyle() {
                override fun updateDrawState(paint: TextPaint) {
                    val progress = ((SystemClock.uptimeMillis() - reveal.began) / 150f).coerceIn(0f, 1f)
                    val opacity = 0.12f + 0.88f * (1f - (1f - progress) * (1f - progress))
                    paint.alpha = (paint.alpha * opacity).toInt()
                }
            }, reveal.start, reveal.end, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        previous = body
        return styled
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (reveals.any { SystemClock.uptimeMillis() - it.began < 150 }) postInvalidateOnAnimation()
    }
}
