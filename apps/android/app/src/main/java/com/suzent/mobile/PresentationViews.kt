package com.suzent.mobile

import android.widget.TextView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.BorderStroke
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.viewinterop.AndroidView
import io.noties.markwon.Markwon
import io.noties.markwon.ext.tables.TablePlugin
import io.noties.markwon.ext.strikethrough.StrikethroughPlugin

@Composable
fun SuzentTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) darkColorScheme(
        primary = Color(PresentationTokens.yellow), onPrimary = Color.Black,
        secondaryContainer = Color(PresentationTokens.yellow), onSecondaryContainer = Color.Black,
        surface = Color(PresentationTokens.surface_dark), background = Color(PresentationTokens.surface_dark), outline = Color.White
    ) else lightColorScheme(
        primary = Color.Black, onPrimary = Color(PresentationTokens.yellow),
        secondaryContainer = Color(PresentationTokens.yellow), onSecondaryContainer = Color.Black,
        surface = Color.White, background = Color.White, outline = Color.Black
    )
    val typography = Typography()
    MaterialTheme(colorScheme = colors, typography = typography.copy(
        titleLarge = typography.titleLarge.copy(fontSize = PresentationTokens.typeTitle.sp, fontWeight = FontWeight.Bold),
        bodyLarge = typography.bodyLarge.copy(fontSize = PresentationTokens.typeBody.sp),
        bodySmall = typography.bodySmall.copy(fontSize = PresentationTokens.typeCaption.sp)
    ), shapes = Shapes(
        small = RoundedCornerShape(0.dp), medium = RoundedCornerShape(0.dp), large = RoundedCornerShape(0.dp)
    ), content = content)
}

@Composable
fun MarkdownText(text: String) {
    val context = LocalContext.current
    val renderer = remember(context) { Markwon.builder(context)
        .usePlugin(TablePlugin.create(context)).usePlugin(StrikethroughPlugin.create()).build() }
    val foreground = MaterialTheme.colorScheme.onSurface.toArgb()
    val link = Color(PresentationTokens.blue).toArgb()
    AndroidView(modifier = Modifier.fillMaxWidth(), factory = { ctx ->
        TextView(ctx).apply { textSize = 16f; setTextIsSelectable(true); setLineSpacing(0f, 1.2f) }
    }, update = { view ->
        view.setTextColor(foreground); view.setLinkTextColor(link)
        if (view.tag != text) { renderer.setMarkdown(view, text); view.tag = text }
    })
}

@Composable
fun MessageView(message: DisplayMessage) {
    val user = message.role == "user"
    val outline = MaterialTheme.colorScheme.outline
    Column(Modifier.fillMaxWidth().then(if (user) Modifier.padding(start = 24.dp, end = 2.dp)
        .drawBehind { drawRect(outline, topLeft = Offset(PresentationTokens.shadowOffset.dp.toPx(), PresentationTokens.shadowOffset.dp.toPx())) }
        .background(Color(PresentationTokens.yellow))
        .border(PresentationTokens.borderWidth.dp, outline).padding(14.dp) else Modifier.padding(vertical = 6.dp)),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (message.text.isNotBlank()) {
            Text(stringResource(if (user) R.string.you else if (message.role == "assistant") R.string.app_name else R.string.activity),
                color = if (user) Color.Black else MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.labelSmall)
            if (user) SelectionContainer { Text(message.text, color = Color.Black) }
            else MarkdownText(message.text)
        }
        message.activities.forEach { part ->
            var expanded by remember(part) { mutableStateOf(false) }
            OutlinedCard(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text((if (expanded) "−  " else "+  ") + when (part.type) {
                        "tool" -> part.toolName.ifEmpty { stringResource(R.string.tool_activity) }
                        "reasoning" -> stringResource(R.string.reasoning)
                        else -> stringResource(R.string.unsupported_activity)
                    }, style = MaterialTheme.typography.labelLarge)
                    if (expanded) SelectionContainer {
                        Text(listOf(part.args, part.output, part.text).filter { it.isNotBlank() }.joinToString("\n\n")
                            .ifEmpty { stringResource(R.string.activity_on_desktop) }, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}

@Composable
fun SuzentAction(label: String, onClick: () -> Unit, prominent: Boolean = false, enabled: Boolean = true) {
    val outline = MaterialTheme.colorScheme.outline
    Button(onClick = onClick, enabled = enabled, shape = RectangleShape,
        border = BorderStroke(PresentationTokens.borderWidth.dp, outline),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (prominent) Color(PresentationTokens.yellow) else MaterialTheme.colorScheme.surface,
            contentColor = if (prominent) Color.Black else MaterialTheme.colorScheme.onSurface),
        modifier = Modifier.fillMaxWidth().padding(end = 2.dp, bottom = 2.dp).drawBehind {
            if (enabled) drawRect(outline, topLeft = Offset(PresentationTokens.shadowOffset.dp.toPx(), PresentationTokens.shadowOffset.dp.toPx()))
        }, contentPadding = PaddingValues(PresentationTokens.spacePage.dp)) {
        Text(label, style = MaterialTheme.typography.titleMedium)
    }
}
