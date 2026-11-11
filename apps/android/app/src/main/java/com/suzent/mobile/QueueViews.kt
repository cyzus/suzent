package com.suzent.mobile

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale

/** Messages waiting for the running turn to end; any of them can redirect now instead, or be dropped. */
@Composable
fun QueuedMessages(model: MobileModel) {
    val items = model.queued
    if (items.isEmpty()) return
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.queued_count, items.size).uppercase(Locale.getDefault()), Modifier.weight(1f),
                fontSize = PresentationTokens.typeLabel.sp, fontWeight = FontWeight.Bold, color = muted)
            if (items.size > 1) SuzentTextButton(onClick = model::clearQueued, contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)) {
                Text(stringResource(R.string.queued_clear), fontSize = PresentationTokens.typeLabel.sp, color = muted)
            }
        }
        items.forEach { item ->
            Row(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outlineVariant)
                .padding(start = 10.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    if (item.text.isNotEmpty()) Text(item.text, fontSize = 14.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    if (item.attachments.isNotEmpty()) Text(item.attachments.joinToString { it.name }, fontSize = 11.sp, color = muted,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                if (model.redirectSupported && item.text.isNotEmpty())
                    SuzentTextButton(onClick = { model.redirectQueued(item) }, enabled = !model.busy,
                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)) {
                        Text(stringResource(R.string.queued_redirect), fontSize = PresentationTokens.typeLabel.sp, fontWeight = FontWeight.Bold)
                    }
                SuzentIconButton(onClick = { model.removeQueued(item) }, label = stringResource(R.string.queued_remove)) {
                    Icon(painterResource(R.drawable.ic_close), contentDescription = null, modifier = Modifier.size(16.dp))
                }
            }
        }
    }
}
