package com.suzent.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
internal fun MailboxEventCard(item: MailboxItem, target: Chat?, expanded: Boolean, busy: Boolean,
                             toggle: () -> Unit, read: () -> Unit, open: (Chat) -> Unit, count: Int = 1, threadUnread: Boolean = item.unread, compact: Boolean = false, history: (@Composable () -> Unit)? = null) {
    val presentation = item.display
    var original by remember(item.id, expanded) { mutableStateOf(false) }
    val ink = MaterialTheme.colorScheme.onSurface
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val accent = suzentYellow()
    Column(Modifier.padding(horizontal = if (compact) 0.dp else 16.dp).fillMaxWidth()
        .background(if (threadUnread || expanded) ink.copy(alpha = .025f) else androidx.compose.ui.graphics.Color.Transparent)) {
        Column(Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = toggle).padding(horizontal = 4.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (!compact) Icon(painterResource(if (presentation.icon == "code") R.drawable.ic_event_branch else R.drawable.ic_inbox),
                    null, Modifier.size(14.dp), tint = muted)
                val heading = if (!compact) presentation.context ?: presentation.source else presentation.detail?.let {
                    listOfNotNull(presentation.activity?.let { action -> stringResource(mailboxActionLabel(action)) }, it).joinToString(" · ")
                } ?: presentation.activity?.let { stringResource(mailboxActionLabel(it)) } ?: presentation.title
                Text(heading, Modifier.weight(1f), fontSize = 11.sp, fontWeight = FontWeight.Medium, color = muted, maxLines = if (compact) 3 else 1, overflow = TextOverflow.Ellipsis)
                if (!compact && count > 1) Text(stringResource(R.string.mailbox_event_count, count), fontSize = 10.sp, color = muted)
                if (threadUnread) Box(Modifier.size(5.dp).background(accent))
                Text(formattedTimestamp(item.createdAt), fontSize = 10.sp, color = muted)
                SuzentChevron(expanded, size = 11.dp, tint = muted)
            }
            if (!compact) Text(presentation.title, fontSize = 14.sp, lineHeight = 19.sp, fontWeight = FontWeight.SemiBold,
                color = ink, maxLines = if (expanded) Int.MAX_VALUE else 2, overflow = TextOverflow.Ellipsis)
            if (!compact && count == 1 && presentation.detail == null) presentation.activity?.let { action ->
                Text(stringResource(mailboxActionLabel(action)), fontSize = 10.sp, color = muted)
            }
            presentation.detail?.takeIf { count == 1 && !compact }?.let { name ->
                Text(listOfNotNull(presentation.activity?.let { stringResource(mailboxActionLabel(it)) }, name).joinToString(" · "),
                    fontSize = 11.sp, color = muted)
            }
        }
        if (expanded && history != null) history()
        if (expanded && history == null) {
            HorizontalDivider(Modifier.padding(horizontal = 14.dp), thickness = .5.dp, color = MaterialTheme.colorScheme.outline.copy(alpha = .4f))
            Column(Modifier.padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                if (item.unread) TextButton(read, enabled = !busy) { Text(stringResource(R.string.mailbox_read), color = ink, fontSize = 12.sp) }
                if (item.chatId != null) Row(Modifier.fillMaxWidth().heightIn(min = 56.dp)
                    .clickable(enabled = target != null, role = Role.Button) { target?.let(open) }.padding(vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Icon(painterResource(R.drawable.ic_tool_chat_bubble_left_right), null, Modifier.size(17.dp), tint = muted)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text(stringResource(R.string.mailbox_destination), fontSize = 10.sp, color = muted)
                        Text(target?.title?.takeIf { it.isNotBlank() } ?: stringResource(R.string.mailbox_destination_unavailable),
                            fontSize = 13.sp, fontWeight = FontWeight.Medium, color = ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        target?.projectName?.takeIf { it.isNotBlank() }?.let { Text(it, fontSize = 10.sp, color = muted) }
                    }
                    if (target != null) SuzentChevron(false, size = 12.dp, tint = muted)
                }
                if (item.payload.isNotBlank()) {
                    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).clickable(role = Role.Button) { original = !original },
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        SuzentChevron(original, size = 11.dp, tint = muted)
                        Text(stringResource(R.string.mailbox_original), fontSize = 11.sp, color = muted)
                    }
                    if (original) Column(Modifier.padding(bottom = 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(item.eventType, fontSize = 10.sp, color = muted)
                        SelectionContainer { Text(item.payload, Modifier.fillMaxWidth().background(ink.copy(alpha = .04f)).padding(10.dp),
                            fontSize = 12.sp, lineHeight = 18.sp, fontFamily = FontFamily.Monospace, color = ink) }
                    }
                }
            }
        }
        HorizontalDivider(thickness = .5.dp, color = MaterialTheme.colorScheme.outline.copy(alpha = .35f))
    }
}

private fun mailboxActionLabel(action: String): Int = when (action) {
    "created" -> R.string.mailbox_action_opened
    "closed" -> R.string.mailbox_action_closed
    "reopened" -> R.string.mailbox_action_reopened
    "updated" -> R.string.mailbox_action_synchronize
    "edited" -> R.string.mailbox_action_edited
    "label_added" -> R.string.mailbox_action_labeled
    "label_removed" -> R.string.mailbox_action_unlabeled
    "assigned" -> R.string.mailbox_action_assigned
    "unassigned" -> R.string.mailbox_action_unassigned
    "review_ready" -> R.string.mailbox_action_ready_for_review
    "draft" -> R.string.mailbox_action_converted_to_draft
    else -> R.string.mailbox_event
}
