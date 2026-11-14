package com.suzent.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** The desktop's unread count: a yellow block with black figures, used by the tab bar and the filters. */
@Composable
internal fun SuzentCountBadge(count: Int, modifier: Modifier = Modifier) {
    Text(if (count > 99) "99+" else count.toString(), modifier.background(suzentYellow()).border(1.dp, Color.Black)
        .padding(horizontal = 4.dp), fontSize = 10.sp, lineHeight = 15.sp, fontWeight = FontWeight.Bold,
        fontFamily = FontFamily.Monospace, color = Color.Black, maxLines = 1)
}

/** What sent an inbox thread: a kind icon, or the source's initials. */
@Composable
internal fun MailboxSourceMark(item: MailboxItem, size: Dp = 32.dp) {
    val muted = item.status == "unrouted"
    val tint = if (muted) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface
    val icon = when (item.sourceKind) {
        "schedule" -> R.drawable.ic_clock
        "agent_inbox" -> R.drawable.ic_tool_chat_bubble_left_right
        "peer" -> R.drawable.ic_desktop
        "email" -> R.drawable.ic_mail
        else -> if (item.display.icon == "code") R.drawable.ic_event_branch else null
    }
    Box(Modifier.size(size).background(MaterialTheme.colorScheme.surface)
        .border(1.dp, if (muted) suzentRowDivider else MaterialTheme.colorScheme.outline), contentAlignment = Alignment.Center) {
        if (icon != null) Icon(painterResource(icon), null, Modifier.size(size * .5f), tint = tint)
        else Text(item.source.filter { it.isLetterOrDigit() }.take(2).uppercase().ifEmpty { "?" }, fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold, fontFamily = FontFamily.Monospace, color = tint)
    }
}

/** Where an inbox event went, styled by what happened to it. */
@Composable
internal fun MailboxStatusPill(status: String, target: Chat?) {
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val tint = when (status) {
        "error" -> MaterialTheme.colorScheme.error
        "queued" -> suzentWarning
        "notified" -> suzentInfo
        "routed" -> MaterialTheme.colorScheme.onSurface
        else -> muted
    }
    val label = when (status) {
        "error" -> stringResource(R.string.mailbox_status_error)
        "queued" -> stringResource(R.string.mailbox_status_queued)
        "notified" -> stringResource(R.string.mailbox_status_notified)
        "unrouted" -> stringResource(R.string.mailbox_status_unrouted)
        else -> target?.title?.takeIf { it.isNotBlank() } ?: stringResource(R.string.mailbox_status_delivered)
    }
    val icon = when (status) {
        "error" -> R.drawable.ic_alert
        "queued" -> R.drawable.ic_inbox
        "notified" -> R.drawable.ic_bell
        "routed" -> R.drawable.ic_arrow_turn
        else -> null
    }
    val divider = suzentRowDivider
    val plain = status == "routed" || status == "unrouted"
    Row(Modifier.heightIn(min = 20.dp).background(if (plain) Color.Transparent else tint.copy(alpha = .08f))
        .drawBehind {
            val stroke = Stroke(1.dp.toPx(), pathEffect = if (status == "unrouted") PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 2.dp.toPx())) else null)
            val inset = .5.dp.toPx()
            drawRect(if (status == "routed") divider else tint.copy(alpha = .6f), Offset(inset, inset),
                size.copy(size.width - 2 * inset, size.height - 2 * inset), style = stroke)
        }
        .padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        if (icon != null) Icon(painterResource(icon), null, Modifier.size(10.dp), tint = tint)
        Text(label, fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = tint, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
internal fun MailboxThreadRow(thread: MailboxThread, target: Chat?, open: () -> Unit) {
    val latest = thread.latest
    val unread = thread.unreadIds.isNotEmpty()
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val meta = listOfNotNull(latest.display.context ?: latest.display.source,
        "×${thread.items.size}".takeIf { thread.items.size > 1 }, formattedTimestamp(latest.createdAt).ifBlank { null }).joinToString(" · ")
    Column {
        Row(Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = open).padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            MailboxSourceMark(latest)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    if (unread) Box(Modifier.padding(top = 6.dp).size(7.dp).background(suzentYellow()).border(1.dp, MaterialTheme.colorScheme.outline))
                    Text(latest.display.title, fontSize = 14.sp, lineHeight = 19.sp, fontWeight = if (unread) FontWeight.SemiBold else FontWeight.Normal,
                        color = if (latest.status == "unrouted") muted else MaterialTheme.colorScheme.onSurface, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(meta, Modifier.weight(1f), fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    MailboxStatusPill(latest.status, target)
                }
            }
        }
        HorizontalDivider(thickness = 1.dp, color = suzentRowDivider)
    }
}

/** One inbox thread on its own page: what it is, where it went, its history and the latest raw event. */
@Composable
internal fun MailboxThreadDetail(model: MobileModel, key: String, back: () -> Unit, openChat: (Chat) -> Unit) {
    val thread = mailboxThreads(model.mailbox.items).firstOrNull { it.key == key }
    LaunchedEffect(key) { thread?.unreadIds?.takeIf { it.isNotEmpty() }?.let { model.readMailbox(it) } }
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val ink = MaterialTheme.colorScheme.onSurface
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface)) {
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(back) { Icon(painterResource(R.drawable.ic_chat_back), stringResource(R.string.mailbox_title), tint = ink) }
            Text(thread?.latest?.display?.source.orEmpty(), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, maxLines = 1)
        }
        HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
        if (thread == null) {
            Text(stringResource(R.string.mailbox_event_unavailable), Modifier.padding(32.dp), color = muted, fontSize = 14.sp)
            return@Column
        }
        val latest = thread.latest
        val target = latest.chatId?.let { model.mailboxChats[it] }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).padding(bottom = 24.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MailboxSourceMark(latest, 36.dp)
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(latest.display.source, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = ink)
                    latest.display.context?.let { Text(it, fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = muted, maxLines = 1) }
                }
            }
            SelectionContainer {
                Text(latest.display.title, Modifier.padding(top = 16.dp), fontSize = 18.sp, lineHeight = 25.sp, fontWeight = FontWeight.SemiBold, color = ink)
            }
            Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MailboxStatusPill(latest.status, target)
                Text(formattedTimestamp(latest.createdAt), fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = muted)
            }
            if (latest.chatId != null) {
                MailboxSection(stringResource(R.string.mailbox_destination))
                MailboxConversationRow(target, openChat)
            }
            if (thread.items.size > 1) {
                MailboxSection(stringResource(R.string.mailbox_activity, thread.items.size))
                thread.items.forEachIndexed { index, item ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Box(Modifier.size(6.dp).background(if (index == 0) ink else muted.copy(alpha = .5f)))
                        Text(mailboxActivityText(item), Modifier.weight(1f), fontSize = 13.sp, color = ink,
                            fontWeight = if (item.unread) FontWeight.SemiBold else FontWeight.Normal)
                        Text(formattedTimestamp(item.createdAt), fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = muted)
                    }
                    HorizontalDivider(thickness = 1.dp, color = suzentRowDivider.copy(alpha = .6f))
                }
            }
            if (latest.payload.isNotBlank()) {
                MailboxSection(stringResource(R.string.mailbox_original))
                SelectionContainer {
                    Text(latest.payload, Modifier.fillMaxWidth().heightIn(max = 240.dp).background(Color(PresentationTokens.background_dark))
                        .border(1.dp, MaterialTheme.colorScheme.outline).verticalScroll(rememberScrollState()).padding(12.dp),
                        fontSize = 12.sp, lineHeight = 18.sp, fontFamily = FontFamily.Monospace, color = Color(PresentationTokens.text_dark))
                }
                Text(latest.eventType, Modifier.padding(top = 6.dp), fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = muted)
            }
        }
    }
}

/** The related conversation, drawn like a row in the conversation list. */
@Composable
private fun MailboxConversationRow(target: Chat?, open: (Chat) -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val muted = if (pressed) Color.Black else MaterialTheme.colorScheme.onSurfaceVariant
    Row(Modifier.fillMaxWidth().background(if (pressed) suzentYellow() else Color.Transparent)
        .clickable(interaction, null, enabled = target != null, role = Role.Button) { target?.let(open) }
        .heightIn(min = 44.dp).padding(vertical = PresentationTokens.spaceRow.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(target?.title?.takeIf { it.isNotBlank() } ?: stringResource(R.string.mailbox_destination_unavailable),
                color = if (target == null) muted else if (pressed) Color.Black else MaterialTheme.colorScheme.onSurface,
                fontSize = PresentationTokens.typeCaption.sp, lineHeight = 18.sp, fontWeight = FontWeight.Medium,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            target?.projectName?.takeIf { it.isNotBlank() }?.let {
                Text(it, fontSize = PresentationTokens.typeSidebarSection.sp, lineHeight = 14.sp, fontWeight = FontWeight.Medium,
                    color = muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        if (target?.running == true) Box(Modifier.padding(start = 8.dp)) { StreamingPulse() }
    }
    HorizontalDivider(thickness = 1.dp, color = suzentRowDivider.copy(alpha = .6f))
}

@Composable
private fun MailboxSection(title: String) {
    Text(title, Modifier.padding(top = 24.dp, bottom = 8.dp), fontSize = 11.sp, fontFamily = FontFamily.Monospace,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/** A thread step: its activity, and the label or detail it touched; plain events fall back to their title. */
@Composable
internal fun mailboxActivityText(item: MailboxItem): String {
    val presentation = item.display
    val action = presentation.activity?.let { mailboxActionLabel(it) } ?: return presentation.title
    return listOfNotNull(stringResource(action), presentation.detail).joinToString(" · ")
}

private fun mailboxActionLabel(action: String): Int? = when (action) {
    "created" -> R.string.mailbox_action_opened
    "closed" -> R.string.mailbox_action_closed
    "reopened" -> R.string.mailbox_action_reopened
    "updated" -> R.string.mailbox_action_updated
    "edited" -> R.string.mailbox_action_edited
    "label_added" -> R.string.mailbox_action_labeled
    "label_removed" -> R.string.mailbox_action_unlabeled
    "assigned" -> R.string.mailbox_action_assigned
    "unassigned" -> R.string.mailbox_action_unassigned
    "review_ready" -> R.string.mailbox_action_ready_for_review
    "draft" -> R.string.mailbox_action_converted_to_draft
    else -> null
}
