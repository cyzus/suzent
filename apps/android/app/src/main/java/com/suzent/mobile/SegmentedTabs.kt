package com.suzent.mobile

import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun <T> SuzentSegmentedTabs(
    options: List<T>,
    selection: T,
    select: (T) -> Unit,
    label: @Composable (T) -> String,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    require(options.isNotEmpty() && selection in options)
    val dark = isSystemInDarkTheme()
    val block = if (dark) suzentYellow() else Color(PresentationTokens.black)
    val blockText = if (dark) Color.Black else Color.White
    BoxWithConstraints(modifier.fillMaxWidth().alpha(if (enabled) 1f else PresentationTokens.disabledAlpha.toFloat())
        .background(Color(if (dark) PresentationTokens.code_header_dark else PresentationTokens.code_bg))
        .border(1.dp, MaterialTheme.colorScheme.outline).padding(3.dp)) {
        val segment = maxWidth / options.size
        val slider by animateDpAsState(segment * options.indexOf(selection), tween(300), label = "segmented tab selection")
        Box(Modifier.matchParentSize()) {
            Box(Modifier.offset(x = slider).width(segment).fillMaxHeight().background(block))
        }
        Row(Modifier.fillMaxWidth().selectableGroup()) {
            options.forEach { option ->
                val selected = option == selection
                Box(Modifier.weight(1f).heightIn(min = 40.dp)
                    .selectable(selected, enabled = enabled, role = Role.Tab) { select(option) }
                    .padding(horizontal = 4.dp, vertical = 8.dp), contentAlignment = Alignment.Center) {
                    Text(label(option), fontSize = PresentationTokens.typeCaption.sp,
                        fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                        color = if (selected) blockText else MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}
