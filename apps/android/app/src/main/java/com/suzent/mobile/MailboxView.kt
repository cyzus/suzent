package com.suzent.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

private enum class InboxSection(val label: Int) {
    NOTIFICATIONS(R.string.mailbox_notifications), TASKS(R.string.tab_tasks), ALL(R.string.mailbox_all)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MailboxView(model: MobileModel, openChat: (Chat) -> Unit) {
    val scope = rememberCoroutineScope()
    var section by rememberSaveable { mutableStateOf(if (model.mailboxCategory == "all") InboxSection.ALL else InboxSection.NOTIFICATIONS) }
    var refreshing by remember { mutableStateOf(false) }
    var expanded by remember(model.mailboxCategory, model.device?.id) { mutableStateOf(setOf<String>()) }
    LaunchedEffect(model.device?.id) { model.refreshMailbox().join() }
    Column(Modifier.fillMaxSize().statusBarsPadding().background(MaterialTheme.colorScheme.surface)) {
        TabTitle(stringResource(R.string.mailbox_title), model)
        SuzentSegmentedTabs(
            options = InboxSection.entries,
            selection = section,
            select = { item ->
                section = item
                if (item != InboxSection.TASKS) model.changeMailbox(if (item == InboxSection.ALL) "all" else "notifications")
            },
            label = { stringResource(it.label) },
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            enabled = !model.mailboxBusy,
        )
        if (section == InboxSection.TASKS) {
            InboxTasks(model, openChat)
        } else if (!model.mailboxSupported) {
            InboxEmpty(stringResource(R.string.mailbox_unsupported))
        } else {
            if (model.mailbox.unread > 0) Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 12.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Text(stringResource(R.string.mailbox_unread, model.mailbox.unread), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                TextButton({ model.readMailbox() }, enabled = !model.mailboxBusy) {
                    Text(stringResource(R.string.mailbox_read_all), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurface)
                }
            }
            PullToRefreshBox(isRefreshing = refreshing, modifier = Modifier.weight(1f), onRefresh = {
                refreshing = true
                scope.launch { try { model.refresh().join() } finally { refreshing = false } }
            }) {
                LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
                    model.mailboxError?.let { error -> item {
                        Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp)) {
                            Text(error, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
                            TextButton({ model.refreshMailbox() }) { Text(stringResource(R.string.refresh)) }
                        }
                    } }
                    if (model.device?.permissions?.allChats != true) item {
                        Text(stringResource(R.string.mailbox_scoped), Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
                            fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    if (model.mailbox.items.isEmpty() && model.mailboxError == null && !model.mailboxLoading) item { InboxEmpty(stringResource(R.string.mailbox_empty)) }
                    items(mailboxThreads(model.mailbox.items), key = { it.key }) { thread ->
                        val item = thread.latest
                        MailboxEventCard(item, item.chatId?.let { model.mailboxChats[it] }, thread.key in expanded, model.mailboxBusy,
                            toggle = {
                                if (thread.key in expanded) expanded = expanded - thread.key
                                else { expanded = expanded + thread.key; if (thread.unreadIds.isNotEmpty()) model.readMailbox(thread.unreadIds) }
                            }, read = { model.readMailbox(thread.unreadIds) }, open = openChat,
                            count = thread.items.size, threadUnread = thread.unreadIds.isNotEmpty(),
                            history = if (thread.items.size > 1) ({
                                var selected by remember(thread.key) { mutableStateOf<Int?>(null) }
                                Column(Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) {
                                    thread.items.forEach { event ->
                                        key(event.id) {
                                            MailboxEventCard(event, event.chatId?.let { model.mailboxChats[it] }, selected == event.id, model.mailboxBusy,
                                                toggle = { selected = if (selected == event.id) null else event.id },
                                                read = { model.readMailbox(listOf(event.id)) }, open = openChat, compact = true)
                                        }
                                    }
                                }
                            }) else null)
                    }
                    if (model.mailbox.hasMore || model.mailboxLoading) item {
                        Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                            if (model.mailboxLoading) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                            else TextButton({ model.loadMoreMailbox() }, enabled = !model.mailboxBusy) {
                                Text(stringResource(R.string.mailbox_load_more), color = MaterialTheme.colorScheme.onSurface)
                            }
                        }
                    }

                }
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
