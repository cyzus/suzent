package com.suzent.mobile

import android.animation.ValueAnimator
import androidx.compose.runtime.Composable

@Composable
fun StreamingMarkdown(text: String, active: Boolean, citationSources: List<CitationSource>) {
    MarkdownText(streamingMarkdown(text, active), citationSources,
        softStreaming = active && ValueAnimator.areAnimatorsEnabled())
}
