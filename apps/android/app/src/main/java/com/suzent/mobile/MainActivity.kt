package com.suzent.mobile

import android.os.Bundle
import android.animation.ValueAnimator
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val model: MobileModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { SuzentTheme { MobileScreen(model) } }
    }
    override fun onStart() { super.onStart(); model.setForeground(true) }
    override fun onStop() { model.setForeground(false); super.onStop() }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MobileScreen(model: MobileModel) {
    var showSettings by rememberSaveable { mutableStateOf(false) }
    var repairScanner by remember { mutableStateOf(false) }
    if (repairScanner) PairingScanner(model) { repairScanner = false }
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    LaunchedEffect(Unit) { if (model.canReconnect && !model.connected) model.connect() }
    LaunchedEffect(model.connected) {
        if (model.connected) { drawer.close(); model.watchNavigation() }
        else { showSettings = false; drawer.close() }
    }
    ModalNavigationDrawer(drawerState = drawer, gesturesEnabled = model.connected, drawerContent = {
        if (model.connected) ModalDrawerSheet(modifier = Modifier.width(PresentationTokens.sidebarWidth.dp), drawerShape = RectangleShape, drawerContainerColor = MaterialTheme.colorScheme.surface) {
            Sidebar(model, showSettings,
                close = { scope.launch { drawer.close() } },
                open = { chat -> focus.clearFocus(); model.open(chat); showSettings = false; scope.launch { drawer.close() } },
                create = { projectId -> model.create(projectId); showSettings = false; scope.launch { drawer.close() } },
                settings = { focus.clearFocus(); showSettings = true; scope.launch { drawer.close() } })
        }
    }) {
        Scaffold(topBar = {
            Column(Modifier.statusBarsPadding()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    if (model.connected) {
                        val label = stringResource(R.string.open_sidebar)
                        IconButton(onClick = { focus.clearFocus(); scope.launch { drawer.open() } }, modifier = Modifier.size(PresentationTokens.controlHeight.dp)) { Icon(painterResource(R.drawable.ic_menu), contentDescription = label, tint = MaterialTheme.colorScheme.onSurface) }
                    }
                    Box(Modifier.weight(1f)) { SuzentWordmark() }
                    if (model.connected) IconButton(onClick = { focus.clearFocus(); model.create(); showSettings = false }, modifier = Modifier.size(PresentationTokens.controlHeight.dp),
                        enabled = !model.busy && !model.streaming && model.device?.permissions?.createChats == true) { Icon(painterResource(R.drawable.ic_new_chat), contentDescription = stringResource(R.string.new_chat)) }
                }
                HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
            }
        }) { padding ->
            Column(Modifier.fillMaxSize().padding(padding).imePadding()) {
                model.error?.let { message ->
                    SuzentNotice(message) { model.error = null }
                }
                when {
                    !model.connected && model.canReconnect -> Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
                        Column(Modifier.widthIn(max = 480.dp).padding(PresentationTokens.spaceLarge.dp), verticalArrangement = Arrangement.spacedBy(20.dp), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
                            SuzentAssistantBadge()
                            Text(stringResource(R.string.reconnect), fontSize = PresentationTokens.typeSection.sp, fontWeight = FontWeight.Bold)
                            if (model.busy) {
                                StreamingPulse()
                                if (model.reconnecting) SuzentAction(stringResource(R.string.cancel_reconnect), model::cancelReconnect)
                            } else SuzentAction(stringResource(R.string.reconnect), model::connect, prominent = true)
                            SuzentAction(stringResource(R.string.pair_again), { model.error = null; repairScanner = true }, enabled = !model.busy && !model.streaming)
                            SuzentAction(stringResource(R.string.forget), model::forget, enabled = !model.busy, quiet = true, destructive = true)
                        }
                    }
                    !model.connected -> Box(Modifier.padding(horizontal = 16.dp)) { PairingView(model) }
                    showSettings -> SettingsView(model)
                    model.selected != null -> Conversation(model)
                    else -> Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = androidx.compose.ui.Alignment.Center) {
                        if (model.busy) CircularProgressIndicator() else Text(stringResource(R.string.select_conversation), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun Sidebar(model: MobileModel, settingsSelected: Boolean, close: () -> Unit, open: (Chat) -> Unit, create: (String?) -> Unit, settings: () -> Unit) {
    var search by rememberSaveable { mutableStateOf("") }
    val listState = rememberLazyListState()
    var observedPinVersion by remember { mutableIntStateOf(model.pinnedVersion) }
    LaunchedEffect(model.pinnedVersion) {
        if (observedPinVersion != model.pinnedVersion) {
            observedPinVersion = model.pinnedVersion
            listState.animateScrollToItem(0)
        }
    }
    var collapsedProjects by remember { mutableStateOf(setOf<String>()) }
    var expandedAgents by remember { mutableStateOf(setOf<String>()) }
    LaunchedEffect(model.selected?.id, model.chats.map { it.id }) {
        var current = model.chats.firstOrNull { it.id == model.selected?.id }
        val parents = mutableSetOf<String>()
        while (current?.isSubagent == true) {
            val parent = current.parentChatId ?: break
            if (!parents.add(parent)) break
            current = model.chats.firstOrNull { it.id == parent }
        }
        expandedAgents = expandedAgents + parents
    }
    fun toggleAgents(id: String) { expandedAgents = if (id in expandedAgents) expandedAgents - id else expandedAgents + id }
    val scheduledIds = remember(model.chats) { scheduledChatIds(model.chats) }
    val normalRows = sidebarChats(model.chats.filter { it.id !in scheduledIds }, search, expandedAgents)
    val projects = remember(model.projects, model.chats) {
        (model.projects + model.chats.mapNotNull { chat -> chat.projectId?.let { Project(it, chat.projectName ?: it) } }).distinctBy { it.id }
    }
    Column(Modifier.fillMaxHeight()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text(stringResource(R.string.chats), fontSize = PresentationTokens.typeSection.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            val label = stringResource(R.string.close_sidebar)
            SuzentTextButton(onClick = close, modifier = Modifier.size(44.dp).semantics { contentDescription = label }) { Text("×") }
        }
        SuzentTextInput(search, { search = it }, stringResource(R.string.search_chats), Modifier.padding(horizontal = 16.dp))
        LazyColumn(Modifier.weight(1f).padding(horizontal = 16.dp), state = listState, contentPadding = PaddingValues(vertical = 12.dp)) {
            if (normalRows.any { it.root.pinned }) {
                item(key = "pinned-heading") { Text(stringResource(R.string.pinned_chats), fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace, fontSize = PresentationTokens.typeControl.sp, modifier = Modifier.padding(vertical = 12.dp)) }
                items(normalRows.filter { it.root.pinned }, key = { it.chat.id }) {
                    SidebarEntry(it, model.selected?.id == it.chat.id && !settingsSelected, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
                }
            }
            projects.forEach { project ->
                item(key = "project:${project.id}") {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        SuzentTextButton(onClick = { collapsedProjects = if (project.id in collapsedProjects) collapsedProjects - project.id else collapsedProjects + project.id }, modifier = Modifier.weight(1f), contentPadding = PaddingValues(0.dp)) {
                            Text((if (project.id in collapsedProjects) "▸ " else "▾ ") + project.name, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace, fontSize = PresentationTokens.typeControl.sp, modifier = Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.onSurface)
                        }
                        val label = stringResource(R.string.new_chat)
                        SuzentTextButton(onClick = { create(project.id) }, enabled = !model.busy && !model.streaming && model.device?.permissions?.createChats == true && model.projects.any { it.id == project.id },
                            modifier = Modifier.size(44.dp).semantics { contentDescription = label }) { Text("+") }
                    }
                }
                if (project.id !in collapsedProjects || search.isNotEmpty()) items(normalRows.filter { !it.root.pinned && it.root.projectId == project.id }, key = { it.chat.id }) {
                    SidebarEntry(it, model.selected?.id == it.chat.id && !settingsSelected, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
                }
            }
            items(normalRows.filter { !it.root.pinned && it.root.projectId == null }, key = { it.chat.id }) {
                SidebarEntry(it, model.selected?.id == it.chat.id && !settingsSelected, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
            }
            val groups = scheduledSidebarGroups(model.chats, model.scheduledTasks, search, expandedAgents)
            if (groups.isNotEmpty()) {
                item(key = "scheduled-heading") { Text(stringResource(R.string.scheduled_tasks), fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace, fontSize = PresentationTokens.typeControl.sp, modifier = Modifier.padding(vertical = 12.dp)) }
                items(groups, key = { it.id }) { group ->
                    Column {
                        val task = group.task
                        val root = group.root
                        if (task != null) ScheduledTaskRow(task, model, !settingsSelected && model.selected?.id == task.chatId,
                            root?.childCount ?: 0, task.chatId in expandedAgents, { task.chatId?.let(::toggleAgents) }) {
                            task.chatId?.let { id -> open(model.chats.firstOrNull { it.id == id } ?: Chat(id, task.name, task.running, emptyList())) }
                        }
                        else if (root != null) SidebarEntry(root, model.selected?.id == root.chat.id && !settingsSelected,
                            model, open, root.chat.id in expandedAgents) { toggleAgents(root.chat.id) }
                        group.children.forEach { entry ->
                            SidebarEntry(entry, model.selected?.id == entry.chat.id && !settingsSelected, model, open, false) {}
                        }
                    }
                }
            }
            if (projects.isEmpty() && model.chats.isEmpty()) item {
                SuzentTextButton(onClick = { create(null) }, enabled = !model.busy && !model.streaming && model.device?.permissions?.createChats == true) { Text(stringResource(R.string.new_chat)) }
            }
        }
        HorizontalDivider()
        SuzentTextButton(onClick = settings, modifier = Modifier.fillMaxWidth().padding(8.dp)) { Text(stringResource(R.string.settings), modifier = Modifier.fillMaxWidth(), fontWeight = FontWeight.Bold) }
    }
}

@Composable
private fun SidebarEntry(entry: SidebarChatEntry, selected: Boolean, model: MobileModel, open: (Chat) -> Unit,
                         expanded: Boolean, toggle: () -> Unit) {
    val rail = MaterialTheme.colorScheme.outlineVariant
    Box(Modifier.padding(start = if (entry.depth > 0) 12.dp else 0.dp).drawBehind {
        if (entry.depth > 0) drawRect(rail, size = Size(1.dp.toPx(), size.height))
    }.padding(start = if (entry.depth > 0) 8.dp else 0.dp)) {
        SidebarChat(entry.chat, selected, model, open, entry.childCount, expanded, toggle, entry.depth > 0)
    }
}

@Composable
private fun SidebarFoldControl(childCount: Int, expanded: Boolean, toggle: () -> Unit) {
    val railColor = MaterialTheme.colorScheme.onSurfaceVariant
            val label = stringResource(if (expanded) R.string.collapse_subagents else R.string.expand_subagents, childCount)
            SuzentTextButton(onClick = toggle, modifier = Modifier.size(width = 52.dp, height = 44.dp).semantics { contentDescription = label },
                contentPadding = PaddingValues(0.dp)) {
                Row(Modifier.background(MaterialTheme.colorScheme.onSurface.copy(alpha = .06f)).padding(horizontal = 7.dp, vertical = 4.dp),
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(childCount.toString(), fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    androidx.compose.foundation.Canvas(Modifier.size(10.dp)) {
                        val path = androidx.compose.ui.graphics.Path().apply {
                            if (expanded) { moveTo(1.dp.toPx(), 3.dp.toPx()); lineTo(5.dp.toPx(), 7.dp.toPx()); lineTo(9.dp.toPx(), 3.dp.toPx()) }
                            else { moveTo(3.dp.toPx(), 1.dp.toPx()); lineTo(7.dp.toPx(), 5.dp.toPx()); lineTo(3.dp.toPx(), 9.dp.toPx()) }
                        }
                        drawPath(path, railColor, style = androidx.compose.ui.graphics.drawscope.Stroke(1.5.dp.toPx()))
                    }
                }
            }
}

@Composable
private fun ScheduledTaskRow(task: ScheduledTask, model: MobileModel, selected: Boolean,
                             childCount: Int, expanded: Boolean, toggle: () -> Unit, open: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(if (selected) MaterialTheme.colorScheme.onSurface.copy(alpha = .08f) else MaterialTheme.colorScheme.surface)
        .clickable(enabled = !model.busy && task.chatId != null, onClick = open).padding(12.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(task.name, fontSize = PresentationTokens.typeChat.sp, fontWeight = FontWeight.SemiBold, maxLines = 2)
            val status = when {
                task.running -> stringResource(R.string.task_running)
                !task.active -> stringResource(R.string.task_paused)
                task.hasError -> stringResource(R.string.task_failed)
                task.nextRunAt != null -> stringResource(R.string.task_next_run, formatTaskDate(task.nextRunAt))
                else -> stringResource(R.string.task_active)
            }
            Text(status, fontSize = PresentationTokens.typeCaption.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (task.chatId == null) Text(stringResource(R.string.task_no_conversation), fontSize = PresentationTokens.typeCaption.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (childCount > 0) SidebarFoldControl(childCount, expanded, toggle)
    }
}

private fun formatTaskDate(raw: String): String = runCatching {
    java.time.OffsetDateTime.parse(raw).atZoneSameInstant(java.time.ZoneId.systemDefault())
        .format(java.time.format.DateTimeFormatter.ofLocalizedDateTime(java.time.format.FormatStyle.SHORT))
}.getOrDefault(raw)

@Composable
private fun SidebarChat(chat: Chat, selected: Boolean, model: MobileModel, open: (Chat) -> Unit,
                        childCount: Int, expanded: Boolean, toggle: () -> Unit, nested: Boolean) {
    var menu by remember { mutableStateOf(false) }
    var moving by remember { mutableStateOf(false) }
    var renaming by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf(false) }
    var title by remember { mutableStateOf("") }
    val outline = MaterialTheme.colorScheme.outline
    val interaction = remember(chat.id) { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val foreground = if (pressed) Color.Black else MaterialTheme.colorScheme.onSurface
    Box {
    Row(Modifier.fillMaxWidth().background(if (pressed) Color(PresentationTokens.yellow) else if (selected) MaterialTheme.colorScheme.onSurface.copy(alpha = 0.08f) else MaterialTheme.colorScheme.surface)
        .drawBehind { if (selected) drawRect(outline, size = Size(3.dp.toPx(), size.height)) }
        .combinedClickable(interactionSource = interaction, indication = null, enabled = !model.busy,
            onLongClickLabel = stringResource(R.string.conversation_actions),
            onLongClick = { moving = false; menu = true }, onClick = { open(chat) })
        .heightIn(min = 48.dp).padding(12.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        if (chat.pinned) Icon(painterResource(R.drawable.ic_chat_pin), null, tint = foreground, modifier = Modifier.padding(end = 6.dp).size(14.dp))
        Column(Modifier.weight(1f)) {
            Text(chat.title, color = foreground, fontSize = PresentationTokens.typeChat.sp, maxLines = 2, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal)
            if (chat.isSubagent && !nested) {
                val parent = model.chats.firstOrNull { it.id == chat.parentChatId }
                Text(if (parent != null) stringResource(R.string.subagent_of, parent.title) else stringResource(R.string.subagent),
                    fontSize = PresentationTokens.typeCaption.sp, color = if (pressed) Color.Black else MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2)
            } else if (chat.isScheduled) Text(stringResource(R.string.scheduled_task), fontSize = PresentationTokens.typeCaption.sp,
                color = if (pressed) Color.Black else MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (chat.running) Text("…", color = suzentLink)
        if (childCount > 0) SidebarFoldControl(childCount, expanded, toggle)
    }
    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }, shape = RectangleShape,
        containerColor = MaterialTheme.colorScheme.surface, tonalElevation = 0.dp,
        modifier = Modifier.width(260.dp).border(2.dp, outline)) {
        if (model.device?.permissions?.manageChats != true) {
            Text(stringResource(R.string.manage_permission_hint), modifier = Modifier.padding(16.dp), fontSize = 13.sp)
        } else if (moving) {
            ChatMenuItem(R.string.move_to_project, R.drawable.ic_chat_back) { moving = false }
            HorizontalDivider(thickness = 2.dp, color = outline)
            model.projects.forEach { project ->
                DropdownMenuItem(text = { Text(project.name, fontWeight = FontWeight.Bold, fontSize = 13.sp) },
                    enabled = project.id != chat.projectId && !model.busy,
                    onClick = { menu = false; model.manageChat(chat, "move", project.id) })
            }
        } else {
            ChatMenuItem(if (chat.pinned) R.string.unpin_chat else R.string.pin_chat, R.drawable.ic_chat_pin) { menu = false; model.manageChat(chat, if (chat.pinned) "unpin" else "pin") }
            ChatMenuItem(R.string.rename_chat, R.drawable.ic_chat_rename) { menu = false; title = chat.title; renaming = true }
            ChatMenuItem(R.string.move_to_project, R.drawable.ic_chat_folder, enabled = !chat.running && model.projects.isNotEmpty()) { moving = true }
            HorizontalDivider(thickness = 2.dp, color = outline)
            ChatMenuItem(R.string.delete_chat, R.drawable.ic_chat_delete, enabled = !chat.running, danger = true) { menu = false; deleting = true }
        }
    }
    }
    if (renaming) AlertDialog(onDismissRequest = { renaming = false }, shape = RectangleShape,
        title = { Text(stringResource(R.string.rename_chat)) },
        text = { SuzentTextInput(title, { title = it }, stringResource(R.string.conversation_title)) },
        confirmButton = { TextButton(enabled = title.trim().isNotEmpty() && title.length <= 200 && !model.busy,
            onClick = { renaming = false; model.manageChat(chat, "rename", title.trim()) }) { Text(stringResource(R.string.save_chat)) } },
        dismissButton = { TextButton(onClick = { renaming = false }) { Text(stringResource(android.R.string.cancel)) } })
    if (deleting) AlertDialog(onDismissRequest = { deleting = false }, shape = RectangleShape,
        title = { Text(stringResource(R.string.delete_chat)) }, text = { Text(stringResource(R.string.delete_chat_warning)) },
        confirmButton = { TextButton(enabled = !model.busy, onClick = { deleting = false; model.manageChat(chat, "delete") }) {
            Text(stringResource(R.string.delete_chat), color = MaterialTheme.colorScheme.error) } },
        dismissButton = { TextButton(onClick = { deleting = false }) { Text(stringResource(android.R.string.cancel)) } })
}

@Composable
private fun ChatMenuItem(label: Int, icon: Int, enabled: Boolean = true, danger: Boolean = false, action: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val background = if (pressed) { if (danger) MaterialTheme.colorScheme.error else Color(PresentationTokens.yellow) } else Color.Transparent
    val foreground = if (pressed) { if (danger) Color.White else Color.Black } else if (danger) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface
    Row(Modifier.fillMaxWidth().background(background).clickable(interactionSource = interaction, indication = null, enabled = enabled, onClick = action)
        .heightIn(min = 44.dp).padding(horizontal = 12.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Icon(painterResource(icon), null, tint = foreground.copy(alpha = if (enabled) 1f else .4f), modifier = Modifier.padding(end = 10.dp).size(18.dp))
        Text(stringResource(label), fontSize = 13.sp, fontWeight = FontWeight.Bold, color = foreground.copy(alpha = if (enabled) 1f else .4f))
    }
}

@Composable
private fun SettingsView(model: MobileModel) {
    var repairScanner by remember { mutableStateOf(false) }
    if (repairScanner) PairingScanner(model) { repairScanner = false }
    var accessExpanded by rememberSaveable { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(PresentationTokens.spacePage.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
        Text(stringResource(R.string.settings), fontSize = PresentationTokens.typeSection.sp, fontWeight = FontWeight.Bold)
        Column(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).padding(16.dp)) {
            Row(Modifier.fillMaxWidth().clickable(role = androidx.compose.ui.semantics.Role.Button) { accessExpanded = !accessExpanded }.heightIn(min = PresentationTokens.controlHeight.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text(stringResource(R.string.access), modifier = Modifier.weight(1f), fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold)
                Text(if (accessExpanded) "−" else "+")
            }
            if (accessExpanded) model.device?.let { Box(Modifier.padding(top = PresentationTokens.spaceMedium.dp)) { ClientPermissionsView(it, model.origin) } }
        }
        Column(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.node_heading), fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.Bold)
            SuzentToggle(stringResource(R.string.enable_node), model.nodeEnabled, model::toggleNode)
            Text(model.nodeStatus, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        SuzentAction(stringResource(R.string.pair_again), { model.error = null; repairScanner = true }, enabled = !model.busy && !model.streaming)
        SuzentAction(stringResource(R.string.forget), model::forget, enabled = !model.busy, quiet = true, destructive = true)
        Text(stringResource(R.string.revoke_help), style = MaterialTheme.typography.bodySmall)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ColumnScope.Conversation(model: MobileModel) {
    val chat = model.selected ?: return
    val expanded = WindowInsets.ime.getBottom(LocalDensity.current) > 0
    val keyboard = LocalSoftwareKeyboardController.current
    val focus = LocalFocusManager.current
    val scroll = remember(chat.id) { androidx.compose.foundation.lazy.LazyListState() }
    LaunchedEffect(model.openedVersion) { scroll.scrollToItem(0) }
    val followLiveGrowth by remember(scroll) {
        derivedStateOf { !scroll.canScrollBackward && !scroll.isScrollInProgress }
    }
    var modelsExpanded by remember(chat.id) { mutableStateOf(false) }
    LaunchedEffect(chat.id) { model.watchApprovals(chat.id) }
    LaunchedEffect(model.sentVersion) {
        if (model.sentVersion > 0) {
            keyboard?.hide(); focus.clearFocus()
            scroll.animateScrollToItem(0)
        }
    }
    val liveTools = model.liveParts.filter { it.type == "tool" }.map { it.toolCallId }.toSet()
    val messages = remember(chat.messages, liveTools) { presentMessages(chat.messages, liveTools) }
    if (chat.id.isNotEmpty()) Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)) {
        chat.projectName?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        Text(if (chat.id.isEmpty()) stringResource(R.string.new_chat) else chat.title, style = MaterialTheme.typography.titleMedium, maxLines = 1)
    }
    LazyColumn(Modifier.weight(1f).fillMaxWidth().pointerInput(Unit) {
        detectTapGestures(onTap = { keyboard?.hide(); focus.clearFocus() })
    }, state = scroll, reverseLayout = chat.id.isNotEmpty(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceLarge.dp)) {
        item(key = "approvals") { ApprovalCards(model) }
        if (model.streaming || model.liveParts.isNotEmpty()) item(key = "live") {
            // The reversed list pins the bottom; smooth line-height changes instead of
            // starting a new scroll animation for every streamed text update.
            val growthModifier = if (model.streaming && model.liveParts.any { it.type == "text" && it.text.isNotBlank() }
                && followLiveGrowth && ValueAnimator.areAnimatorsEnabled()) {
                Modifier.animateContentSize(animationSpec = tween(120, easing = LinearOutSlowInEasing))
            } else Modifier
            Column(modifier = growthModifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
                AssemblyBadge(thinking = showAssemblyBadge(model.liveParts, model.streaming))
                if (model.liveParts.isNotEmpty()) ActivityContent(model.liveParts, live = model.streaming)
            }
        }
        itemsIndexed(messages.asReversed(), key = { index, _ -> "message-${messages.lastIndex - index}" }) { index, message ->
            val idle = !model.busy && !model.streaming && !chat.running
            val lastUser = chat.messages.indexOfLast { it.role == "user" }
            val canReplay = idle && chat.models.isNotEmpty() && lastUser >= 0 && model.device?.permissions?.send == true && model.device?.permissions?.manageChats == true
            MessageView(message, isLatest = index == 0 && !model.streaming && model.liveParts.isEmpty(), fallbackModel = chat.model,
                canRetry = canReplay && (message.messageIndex == lastUser || (index == 0 && message.role == "assistant")),
                canEdit = canReplay && message.role == "user" && message.messageIndex == lastUser,
                canFork = idle && message.role == "assistant" && model.device?.permissions?.createChats == true,
                onAction = { action, text -> model.messageAction(message, action, text) })
        }
        if (chat.id.isEmpty()) item { StartPage(model, chat, expanded) }
    }
    val composerOutline = MaterialTheme.colorScheme.outline
    val composerShadow = suzentShadow
    Box(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp).drawBehind {
        val offset = PresentationTokens.shadowOffset.dp.toPx()
        drawRect(composerShadow, topLeft = androidx.compose.ui.geometry.Offset(offset, offset), size = Size(size.width - offset, size.height - offset))
    }.padding(end = PresentationTokens.shadowOffset.dp, bottom = PresentationTokens.shadowOffset.dp)) {
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
        .border(PresentationTokens.borderWidth.dp, composerOutline).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        PendingAttachmentStrip(model)
        Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        if (model.attachmentsSupported && model.device?.permissions?.send == true)
            AttachButton(model, enabled = !model.busy && model.attachments.size < MAX_ATTACHMENTS)
        BasicTextField(value = model.draft, onValueChange = { model.draft = it }, enabled = !model.busy,
            modifier = Modifier.weight(1f).heightIn(min = 44.dp).padding(horizontal = 4.dp, vertical = 12.dp), minLines = 1, maxLines = if (expanded) 6 else 1,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Default),
            textStyle = MaterialTheme.typography.bodyMedium.copy(fontSize = PresentationTokens.typeChat.sp, color = MaterialTheme.colorScheme.onSurface),
            cursorBrush = androidx.compose.ui.graphics.SolidColor(suzentLink),
            decorationBox = { inner -> Box { if (model.draft.isEmpty()) Text(stringResource(R.string.message), fontSize = PresentationTokens.typeChat.sp, color = MaterialTheme.colorScheme.onSurfaceVariant); inner() } })
        if (!expanded) SendAction(model, chat)
        }
        if (expanded) Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) {
                SuzentSelectionTrigger(model.selectedModel ?: chat.model ?: stringResource(R.string.desktop_model),
                    { modelsExpanded = true; focus.clearFocus(); keyboard?.hide() }, enabled = !model.busy && !model.streaming && chat.models.isNotEmpty() && model.device?.permissions?.send == true)

            }
            SendAction(model, chat)
        }
    }
    }
    if (modelsExpanded) SuzentSelectionPanel(
        title = stringResource(R.string.desktop_model),
        options = listOf("" to stringResource(R.string.conversation_default)) + chat.models.distinct().sorted().map { it to it },
        selected = model.selectedModel.orEmpty(), dismiss = { modelsExpanded = false }
    ) { model.selectModel(it.ifEmpty { null }); modelsExpanded = false }

}

@Composable
private fun SendAction(model: MobileModel, chat: Chat) {
            if (model.streaming || chat.running) SuzentAction(stringResource(R.string.stop), model::stop, prominent = true, enabled = model.device?.permissions?.stop == true, compact = true)
            else SuzentAction(stringResource(R.string.send), model::send, prominent = true,
                enabled = !model.busy && (model.draft.isNotBlank() || model.attachments.isNotEmpty()) && model.device?.permissions?.send == true, compact = true)
}

@Composable
private fun StartPage(model: MobileModel, chat: Chat, keyboardVisible: Boolean) {
    var projectsExpanded by remember { mutableStateOf(false) }
    var hour by remember { mutableIntStateOf(java.time.LocalTime.now().hour) }
    LaunchedEffect(Unit) { while (true) { hour = java.time.LocalTime.now().hour; kotlinx.coroutines.delay(60000) } }
    val greeting = when { hour < 5 -> R.string.greeting_night; hour < 12 -> R.string.greeting_morning; hour < 17 -> R.string.greeting_build; hour < 21 -> R.string.greeting_evening; else -> R.string.greeting_bed }
    Column(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = if (keyboardVisible) 12.dp else 40.dp),
        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(28.dp)) {
        GreetingCube(Modifier.size(if (keyboardVisible) 90.dp else 160.dp))
        Text(stringResource(greeting).uppercase(java.util.Locale.getDefault()), fontSize = 30.sp, lineHeight = 36.sp, fontWeight = FontWeight.Black,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        Box {
            SuzentSelectionTrigger(chat.projectName ?: stringResource(R.string.default_project),
                { projectsExpanded = true }, enabled = !model.busy && model.projects.isNotEmpty(), prefix = stringResource(R.string.creating_in))
            if (projectsExpanded) SuzentSelectionPanel(
                title = stringResource(R.string.creating_in), options = model.projects.map { it.id to it.name },
                selected = chat.projectId.orEmpty(), dismiss = { projectsExpanded = false }
            ) { id ->
                model.selected = model.selected?.copy(projectId = id, projectName = model.projects.first { it.id == id }.name)
                projectsExpanded = false
            }
        }
    }
}
