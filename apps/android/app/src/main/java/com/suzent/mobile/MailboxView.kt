package com.suzent.mobile

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

private enum class InboxFilter(val category: String, val label: Int) {
    ALL("all", R.string.mailbox_all),
    NOTIFICATIONS("notifications", R.string.mailbox_notifications),
    EXTERNAL("external", R.string.mailbox_external),
    AGENT("agent", R.string.mailbox_agent),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MailboxView(model: MobileModel, openChat: (Chat) -> Unit) {
    var showTasks by rememberSaveable { mutableStateOf(false) }
    var openThread by rememberSaveable(model.device?.id) { mutableStateOf<String?>(null) }
    LaunchedEffect(model.device?.id) { model.refreshMailbox().join() }
    BackHandler(enabled = openThread != null || showTasks) { if (openThread != null) openThread = null else showTasks = false }
    openThread?.let { key ->
        Box(Modifier.fillMaxSize().statusBarsPadding()) { MailboxThreadDetail(model, key, back = { openThread = null }, openChat = openChat) }
        return
    }
    Column(Modifier.fillMaxSize().statusBarsPadding().background(MaterialTheme.colorScheme.surface)) {
        InboxHeader(model, showTasks, toggleTasks = { showTasks = !showTasks })
        if (showTasks) InboxTasks(model, openChat)
        else if (!model.mailboxSupported) InboxEmpty(stringResource(R.string.mailbox_unsupported))
        else {
            InboxFilters(model)
            InboxList(model, open = { openThread = it })
        }
    }
}

@Composable
private fun InboxHeader(model: MobileModel, showTasks: Boolean, toggleTasks: () -> Unit) {
    val ink = MaterialTheme.colorScheme.onSurface
    TabTitle(stringResource(if (showTasks) R.string.tab_tasks else R.string.mailbox_title), model) {
        if (showTasks) IconButton(toggleTasks, Modifier.align(Alignment.CenterStart).padding(start = 4.dp)) {
            Icon(painterResource(R.drawable.ic_chat_back), stringResource(R.string.mailbox_title), tint = ink)
        } else if (model.mailboxSupported && model.mailbox.unread > 0) IconButton({ model.readMailbox() },
            Modifier.align(Alignment.CenterStart).padding(start = 4.dp), enabled = !model.mailboxBusy) {
            Icon(painterResource(R.drawable.ic_message_check), stringResource(R.string.mailbox_read_all), tint = ink)
        }
        if (!showTasks) IconButton(toggleTasks, Modifier.align(Alignment.CenterEnd).padding(end = 4.dp)) {
            Icon(painterResource(R.drawable.ic_clock), stringResource(R.string.tab_tasks), Modifier.size(22.dp), tint = ink)
        }
    }
}

@Composable
private fun InboxFilters(model: MobileModel) {
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 10.dp)
        .alpha(if (model.mailboxBusy) PresentationTokens.disabledAlpha.toFloat() else 1f),
        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        // The segmented tabs' block: black in light mode, yellow in dark.
        val dark = isSystemInDarkTheme()
        val block = if (dark) suzentYellow() else Color.Black
        val blockText = if (dark) Color.Black else Color.White
        InboxFilter.entries.forEach { filter ->
            val selected = model.mailboxCategory == filter.category
            Row(Modifier.heightIn(min = 30.dp).background(if (selected) block else MaterialTheme.colorScheme.surface)
                .border(1.dp, if (selected) block else suzentRowDivider)
                .selectable(selected, enabled = !model.mailboxBusy, role = Role.Tab) { if (!selected) model.changeMailbox(filter.category) }
                .padding(horizontal = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(stringResource(filter.label), fontSize = PresentationTokens.typeMeta.sp, fontFamily = FontFamily.Monospace,
                    fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                    color = if (selected) blockText else MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                if (filter == InboxFilter.NOTIFICATIONS && model.mailbox.unread > 0) SuzentCountBadge(model.mailbox.unread)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ColumnScope.InboxList(model: MobileModel, open: (String) -> Unit) {
    val scope = rememberCoroutineScope()
    var refreshing by remember { mutableStateOf(false) }
    val threads = mailboxThreads(model.mailbox.items)
    PullToRefreshBox(isRefreshing = refreshing, modifier = Modifier.weight(1f), onRefresh = {
        refreshing = true
        scope.launch { try { model.refresh().join() } finally { refreshing = false } }
    }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
            item { HorizontalDivider(thickness = 1.dp, color = suzentRowDivider) }
            model.mailboxError?.let { error -> item {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                    Text(error, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
                    TextButton({ model.refreshMailbox() }) { Text(stringResource(R.string.refresh), color = MaterialTheme.colorScheme.onSurface) }
                }
            } }
            if (threads.isEmpty() && model.mailboxError == null && !model.mailboxLoading) item { InboxEmpty(stringResource(R.string.mailbox_empty)) }
            items(threads, key = { it.key }) { thread ->
                MailboxThreadRow(thread, thread.latest.chatId?.let { model.mailboxChats[it] }) { open(thread.key) }
                if (thread.key == threads.last().key) LaunchedEffect(thread.key, model.mailbox.hasMore) {
                    if (model.mailbox.hasMore) model.loadMoreMailbox()
                }
            }
            if (model.mailboxLoading) item {
                Box(Modifier.fillMaxWidth().padding(vertical = 16.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onSurface)
                }
            }
            if (model.device?.permissions?.allChats != true) item {
                Text(stringResource(R.string.mailbox_scoped), Modifier.fillMaxWidth().padding(horizontal = 32.dp, vertical = 16.dp),
                    fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
            }
        }
    }
}

@Composable
private fun InboxEmpty(message: String) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 32.dp, vertical = 64.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Icon(painterResource(R.drawable.ic_inbox), null, Modifier.size(32.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = .5f))
        Text(message, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
