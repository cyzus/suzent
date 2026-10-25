package com.suzent.mobile

import android.os.Bundle
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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
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
    LaunchedEffect(model.connected, model.isDemo) {
        showSettings = false
        if (model.connected) { drawer.close(); model.watchNavigation() }
        else { showSettings = false; drawer.close() }
    }
    ModalNavigationDrawer(drawerState = drawer, gesturesEnabled = model.connected, drawerContent = {
        if (model.connected) {
            val edge = suzentShadow
            ModalDrawerSheet(modifier = Modifier.width(PresentationTokens.sidebarWidth.dp), drawerShape = RectangleShape,
                drawerContainerColor = MaterialTheme.colorScheme.surface, windowInsets = WindowInsets(0, 0, 0, 0)) {
            Box(Modifier.fillMaxSize()) {
            Sidebar(model, showSettings,
                close = { scope.launch { drawer.close() } },
                open = { chat -> focus.clearFocus(); model.open(chat); showSettings = false; scope.launch { drawer.close() } },
                create = { projectId -> model.create(projectId); showSettings = false; scope.launch { drawer.close() } },
                settings = { focus.clearFocus(); showSettings = true; scope.launch { drawer.close() } })
            Box(Modifier.align(androidx.compose.ui.Alignment.CenterEnd).fillMaxHeight().width(PresentationTokens.borderWidthHeavy.dp).background(edge))
            }
            }
        }
    }) {
        Scaffold(topBar = {
            Column(Modifier.statusBarsPadding()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    if (model.connected) {
                        val label = stringResource(R.string.open_sidebar)
                        SuzentIconButton(onClick = { focus.clearFocus(); scope.launch { drawer.open() } }, label = label) {
                            Icon(painterResource(R.drawable.ic_menu), contentDescription = null, modifier = Modifier.size(20.dp))
                        }
                    }
                    Box(Modifier.weight(1f), contentAlignment = androidx.compose.ui.Alignment.Center) {
                        val chat = model.selected
                        if (model.connected && showSettings) {
                            Text(stringResource(R.string.settings), style = MaterialTheme.typography.titleMedium, maxLines = 1)
                        } else if (model.connected && chat != null && chat.id.isNotEmpty()) {
                            Column(Modifier.padding(horizontal = 8.dp), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
                                chat.projectName?.let { Text(it, style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis) }
                                Text(chat.title, style = MaterialTheme.typography.titleMedium, maxLines = 1,
                                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                                    textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                            }
                        } else if (!model.connected && model.canReconnect) {
                            Text("SUZENT", modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp),
                                fontSize = 13.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 2.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        } else SuzentWordmark()
                    }
                    if (model.connected) SuzentIconButton(onClick = { focus.clearFocus(); model.create(); showSettings = false },
                        label = stringResource(R.string.new_chat),
                        enabled = !model.busy && !model.streaming && model.device?.permissions?.createChats == true) {
                        Icon(painterResource(R.drawable.ic_new_chat), contentDescription = null, modifier = Modifier.size(20.dp))
                    }
                }
                if (model.connected || !model.canReconnect) HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
            }
        }) { padding ->
            Column(Modifier.fillMaxSize().padding(padding).imePadding()) {
                if (model.isDemo) {
                    Row(Modifier.fillMaxWidth().background(Color(PresentationTokens.yellow)).padding(horizontal = 16.dp),
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Text(stringResource(R.string.demo_banner), modifier = Modifier.weight(1f), color = Color.Black,
                            style = MaterialTheme.typography.bodySmall)
                        TextButton(onClick = model::exitDemo, enabled = !model.busy) { Text(stringResource(R.string.demo_exit), color = Color.Black) }
                    }
                }
                model.error?.let { message ->
                    SuzentNotice(message) { model.error = null }
                }
                when {
                    !model.connected && model.canReconnect -> {
                        var helpOpen by remember { mutableStateOf(false) }
                        Column(Modifier.fillMaxSize().padding(horizontal = 24.dp).padding(bottom = 20.dp), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
                            Spacer(Modifier.weight(1f))
                            Column(verticalArrangement = Arrangement.spacedBy(21.dp), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
                                ReconnectIndicator(active = model.busy)
                                Text(stringResource(if (model.busy) R.string.connecting_suzent else R.string.reconnect),
                                    fontSize = 21.sp, fontWeight = FontWeight.Medium, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                                Box(Modifier.heightIn(min = 44.dp)) {
                                    if (model.busy) {
                                        if (model.reconnecting) TextButton(onClick = model::cancelReconnect) {
                                            Text(stringResource(R.string.cancel_reconnect), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        }
                                    } else TextButton(onClick = model::connect) {
                                        Text(stringResource(R.string.reconnect), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                }
                            }
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = { helpOpen = true }) {
                                Text(stringResource(R.string.connection_help), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        if (helpOpen) AlertDialog(onDismissRequest = { helpOpen = false },
                            title = { Text(stringResource(R.string.connection_help)) },
                            text = { Column {
                                Text(stringResource(R.string.connection_help_detail))
                                TextButton(onClick = { helpOpen = false; model.error = null; repairScanner = true }, enabled = !model.busy && !model.streaming) { Text(stringResource(R.string.pair_again)) }
                                TextButton(onClick = { helpOpen = false; model.forget() }, enabled = !model.busy) { Text(stringResource(R.string.forget), color = MaterialTheme.colorScheme.error) }
                            } },
                            confirmButton = { TextButton(onClick = { helpOpen = false }) { Text(stringResource(R.string.cancel_reconnect)) } })
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
    var expandedProject by rememberSaveable { mutableStateOf<String?>(null) }
    var showAllScheduled by rememberSaveable { mutableStateOf(false) }
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
    // The backend lists chats newest-first (updated_at desc), so a project's earliest chat
    // index is its latest activity. Mirrors the desktop sidebar's sortedProjects ordering
    // without adding a timestamp to the mobile payload.
    val projects = remember(model.projects, model.chats) {
        val merged = (model.projects + model.chats.mapNotNull { chat -> chat.projectId?.let { Project(it, chat.projectName ?: it) } }).distinctBy { it.id }
        val serverOrder = merged.withIndex().associate { (index, project) -> project.id to index }
        val activity = mutableMapOf<String, Int>()
        model.chats.forEachIndexed { index, chat ->
            val id = chat.projectId ?: return@forEachIndexed
            if (id in serverOrder && id !in activity) activity[id] = index
        }
        merged.sortedWith(compareBy({ activity[it.id] ?: Int.MAX_VALUE }, { serverOrder.getValue(it.id) }))
    }
    val scheduledGroups = scheduledSidebarGroups(model.chats, model.scheduledTasks, search, expandedAgents)
    // Matches the desktop automation preview: five rows, then View all.
    val scheduledPreview = 5
    val visibleScheduledGroups = if (showAllScheduled || search.isNotEmpty()) scheduledGroups else scheduledGroups.take(scheduledPreview)
    val headerShadow = suzentShadow
    Column(Modifier.fillMaxHeight().statusBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp).heightIn(min = PresentationTokens.controlHeight.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text(stringResource(R.string.chats), fontSize = PresentationTokens.typeSection.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            val label = stringResource(R.string.close_sidebar)
            SuzentIconButton(onClick = close, label = label) { Text("×", fontSize = 20.sp, lineHeight = 20.sp) }
        }
        HorizontalDivider(thickness = PresentationTokens.borderWidthHeavy.dp, color = suzentShadow)
        SuzentRowButton(label = stringResource(R.string.new_chat), onClick = { create(null) }, leadingIcon = R.drawable.ic_new_chat,
            enabled = !model.busy && !model.streaming && model.device?.permissions?.createChats == true,
            modifier = Modifier.padding(horizontal = 16.dp).padding(top = 12.dp))
        SuzentTextInput(search, { search = it }, stringResource(R.string.search_chats), Modifier.padding(horizontal = 16.dp).padding(top = 12.dp))
        LazyColumn(Modifier.weight(1f).padding(horizontal = 16.dp), state = listState, contentPadding = PaddingValues(vertical = 12.dp)) {
            if (scheduledGroups.isNotEmpty()) {
                item(key = "scheduled-heading") { SidebarSectionHeading(stringResource(R.string.scheduled_tasks), scheduledGroups.size) }
                items(visibleScheduledGroups, key = { it.id }) { group ->
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
                if (search.isEmpty() && scheduledGroups.size > scheduledPreview) {
                    item(key = "scheduled-view-all") {
                        SuzentTextButton(onClick = { showAllScheduled = !showAllScheduled }, modifier = Modifier.fillMaxWidth()) {
                            Text(stringResource(if (showAllScheduled) R.string.task_show_fewer else R.string.task_view_all, scheduledGroups.size),
                                fontSize = PresentationTokens.typeCaption.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
            if (normalRows.any { it.root.pinned }) {
                item(key = "pinned-heading") { SidebarSectionHeading(stringResource(R.string.pinned_chats)) }
                items(normalRows.filter { it.root.pinned }, key = { it.chat.id }) {
                    SidebarEntry(it, model.selected?.id == it.chat.id && !settingsSelected, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
                }
            }
            projects.forEach { project ->
                val projectOpen = expandedProject == project.id
                val isOpen = projectOpen || search.isNotEmpty()
                item(key = "project:${project.id}") {
                    val projectInteraction = remember { MutableInteractionSource() }
                    val projectPressed by projectInteraction.collectIsPressedAsState()
                    Row(Modifier.fillMaxWidth()
                        .background(if (projectPressed) MaterialTheme.colorScheme.onSurface.copy(alpha = 0.08f) else Color.Transparent)
                        .clickable(interactionSource = projectInteraction, indication = null,
                            role = androidx.compose.ui.semantics.Role.Button) { expandedProject = if (projectOpen) null else project.id }
                        .heightIn(min = 44.dp)
                        .padding(horizontal = 12.dp),
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Text((if (isOpen) "\u25be " else "\u25b8 ") + project.name, fontWeight = FontWeight.SemiBold,
                            fontSize = PresentationTokens.typeCaption.sp, modifier = Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.onSurface)
                    }
                }
                if (isOpen) items(normalRows.filter { !it.root.pinned && it.root.projectId == project.id }, key = { it.chat.id }) {
                    SidebarEntry(it, model.selected?.id == it.chat.id && !settingsSelected, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
                }
            }
            items(normalRows.filter { !it.root.pinned && it.root.projectId == null }, key = { it.chat.id }) {
                SidebarEntry(it, model.selected?.id == it.chat.id && !settingsSelected, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
            }
        }
        HorizontalDivider()
        SuzentTextButton(onClick = settings, modifier = Modifier.navigationBarsPadding().fillMaxWidth().padding(8.dp)) { Text(stringResource(R.string.settings), modifier = Modifier.fillMaxWidth(), fontWeight = FontWeight.Bold) }
    }
}

@Composable
private fun SidebarEntry(entry: SidebarChatEntry, selected: Boolean, model: MobileModel, open: (Chat) -> Unit,
                         expanded: Boolean, toggle: () -> Unit) {
    SidebarChat(entry.chat, selected, model, open, entry.childCount, expanded, toggle, entry.depth > 0)
}

@Composable
private fun SidebarFoldControl(childCount: Int, expanded: Boolean, toggle: () -> Unit,
                               color: Color = MaterialTheme.colorScheme.onSurfaceVariant) {
    val label = stringResource(if (expanded) R.string.collapse_subagents else R.string.expand_subagents, childCount)
    // Inline in the reserved meta slot: 16dp tall, widened by padding for the tap target.
    Row(Modifier.heightIn(min = 16.dp).padding(horizontal = 4.dp)
        .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null,
            role = androidx.compose.ui.semantics.Role.Button, onClick = toggle)
        .semantics(mergeDescendants = true) { contentDescription = label },
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(stringResource(R.string.subagent_count, childCount), fontSize = PresentationTokens.typeSidebarSection.sp,
            lineHeight = 14.sp, fontWeight = FontWeight.Medium, color = color, maxLines = 1)
        androidx.compose.foundation.Canvas(Modifier.size(12.dp).rotate(if (expanded) 90f else 0f)) {
            val path = androidx.compose.ui.graphics.Path().apply {
                moveTo(4.5.dp.toPx(), 2.5.dp.toPx()); lineTo(8.dp.toPx(), 6.dp.toPx()); lineTo(4.5.dp.toPx(), 9.5.dp.toPx())
            }
            drawPath(path, color, style = androidx.compose.ui.graphics.drawscope.Stroke(1.5.dp.toPx()))
        }
    }
}

@Composable
private fun ScheduledTaskRow(task: ScheduledTask, model: MobileModel, selected: Boolean,
                             childCount: Int, expanded: Boolean, toggle: () -> Unit, open: () -> Unit) {
    val selection = suzentSelection
    Row(Modifier.fillMaxWidth().background(if (selected) selection else MaterialTheme.colorScheme.surface)
        .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null,
            enabled = !model.busy && task.chatId != null, onClick = open)
        .heightIn(min = 44.dp).padding(horizontal = 12.dp, vertical = PresentationTokens.spaceRow.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(task.name, fontSize = PresentationTokens.typeCaption.sp, fontWeight = FontWeight.Medium,
                maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            val status = when {
                !task.active -> if (task.unresolvedError) stringResource(R.string.task_paused_failed) else stringResource(R.string.task_paused)
                task.unresolvedError -> stringResource(R.string.task_failed)
                task.nextRunAt != null -> stringResource(R.string.task_next_run, formatTaskDate(task.nextRunAt))
                else -> stringResource(R.string.task_active)
            }
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (task.running) Box(Modifier.size(8.dp).background(suzentLink))
                Text(status, fontSize = PresentationTokens.typeSidebarSection.sp, fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (childCount > 0) {
                    Text("·", fontSize = PresentationTokens.typeSidebarSection.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    SidebarFoldControl(childCount, expanded, toggle)
                }
            }
            if (task.chatId == null) Text(stringResource(R.string.task_no_conversation), fontSize = PresentationTokens.typeCaption.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        val activity = (if (task.failureHandled()) task.chatUpdatedAt else task.lastRunAt)?.let { formatTaskDate(it) }
            ?: stringResource(R.string.task_not_yet)
        Text(activity,
            fontSize = PresentationTokens.typeSidebarSection.sp, fontWeight = FontWeight.Medium,
            style = androidx.compose.ui.text.TextStyle(fontFeatureSettings = "tnum"),
            color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, modifier = Modifier.padding(start = 8.dp))
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
    val selection = suzentSelection
    val rule = suzentRowDivider
    Box {
    Row(Modifier.fillMaxWidth().background(if (pressed) Color(PresentationTokens.yellow) else if (selected) selection else MaterialTheme.colorScheme.surface)
        .drawBehind {
            if (!nested) drawLine(rule, androidx.compose.ui.geometry.Offset(0f, size.height - 1.dp.toPx()),
                androidx.compose.ui.geometry.Offset(size.width, size.height - 1.dp.toPx()), 1.dp.toPx())
        }
        .combinedClickable(interactionSource = interaction, indication = null, enabled = !model.busy,
            onLongClickLabel = stringResource(R.string.conversation_actions),
            onLongClick = { moving = false; menu = true }, onClick = { open(chat) })
        .heightIn(min = 44.dp).padding(start = if (nested) 32.dp else 12.dp, end = 12.dp,
            top = PresentationTokens.spaceRow.dp, bottom = PresentationTokens.spaceRow.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        if (chat.pinned) Icon(painterResource(R.drawable.ic_chat_pin), null, tint = foreground, modifier = Modifier.padding(end = 6.dp).size(12.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(chat.title, color = foreground, fontSize = PresentationTokens.typeCaption.sp, lineHeight = 18.sp,
                fontWeight = FontWeight.Medium, maxLines = 1,
                overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            val muted = if (pressed) Color.Black else MaterialTheme.colorScheme.onSurfaceVariant
            val meta = when {
                chat.isSubagent && !nested -> model.chats.firstOrNull { it.id == chat.parentChatId }
                    ?.let { stringResource(R.string.subagent_of, it.title) } ?: stringResource(R.string.subagent)
                chat.isScheduled -> stringResource(R.string.scheduled_task)
                else -> null
            }
            // Reserved even when empty: chat rows must share one height cadence.
            Row(Modifier.heightIn(min = 16.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                if (meta != null) Text(meta, fontSize = PresentationTokens.typeSidebarSection.sp, lineHeight = 14.sp,
                    fontWeight = FontWeight.Medium, color = muted,
                    maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                if (meta != null && childCount > 0) Text(" · ", fontSize = PresentationTokens.typeSidebarSection.sp,
                    lineHeight = 14.sp, color = muted)
                if (childCount > 0) SidebarFoldControl(childCount, expanded, toggle, muted)
            }
        }
        if (chat.running) Text("…", color = suzentLink)
    }
    val menuShadow = suzentShadow
    val menuSurface = MaterialTheme.colorScheme.surface
    val menuShadowSize = PresentationTokens.shadowOffsetOverlay.dp
    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }, shape = RectangleShape,
        containerColor = Color.Transparent, tonalElevation = 0.dp, shadowElevation = 0.dp,
        modifier = Modifier.width(260.dp)) {
        // The popup's scroll container clips anything drawn outside its bounds, so the offset is
        // reserved inside the content: shadow first, opaque panel over it.
        Box(Modifier.fillMaxWidth().drawBehind {
            val offset = menuShadowSize.toPx()
            drawRect(menuShadow, topLeft = Offset(offset, offset), size = size)
        }.padding(end = menuShadowSize, bottom = menuShadowSize)) {
        Column(Modifier.fillMaxWidth().background(menuSurface).border(PresentationTokens.borderWidth.dp, outline)) {
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
    }
    }
    if (renaming) SuzentDialog(onDismissRequest = { renaming = false }, title = stringResource(R.string.rename_chat)) {
        SuzentTextInput(title, { title = it }, stringResource(R.string.conversation_title))
        Row(Modifier.fillMaxWidth().padding(top = PresentationTokens.spaceMedium.dp), horizontalArrangement = Arrangement.End) {
            SuzentTextButton(onClick = { renaming = false }) { Text(stringResource(android.R.string.cancel)) }
            SuzentTextButton(onClick = { renaming = false; model.manageChat(chat, "rename", title.trim()) },
                enabled = title.trim().isNotEmpty() && title.length <= 200 && !model.busy) { Text(stringResource(R.string.save_chat)) }
        }
    }
    if (deleting) SuzentDialog(onDismissRequest = { deleting = false }, title = stringResource(R.string.delete_chat)) {
        Text(stringResource(R.string.delete_chat_warning), fontSize = PresentationTokens.typeCaption.sp)
        Row(Modifier.fillMaxWidth().padding(top = PresentationTokens.spaceMedium.dp), horizontalArrangement = Arrangement.End) {
            SuzentTextButton(onClick = { deleting = false }) { Text(stringResource(android.R.string.cancel)) }
            SuzentTextButton(onClick = { deleting = false; model.manageChat(chat, "delete") }, enabled = !model.busy) {
                Text(stringResource(R.string.delete_chat), color = MaterialTheme.colorScheme.error)
            }
        }
    }
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
    var aboutExpanded by rememberSaveable { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(PresentationTokens.spacePage.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
        Text(stringResource(R.string.settings), fontSize = PresentationTokens.typeSection.sp, fontWeight = FontWeight.Bold)
        if (model.isDemo) {
            Text(stringResource(R.string.demo_intro))
            Text(stringResource(R.string.demo_limits), style = MaterialTheme.typography.bodySmall)
            SuzentAction(stringResource(R.string.demo_reset), model::resetDemo, enabled = !model.busy)
            SuzentAction(stringResource(R.string.demo_exit), model::exitDemo, enabled = !model.busy)
        } else {
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
            Column(Modifier.fillMaxWidth().border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).padding(16.dp)) {
                Row(Modifier.fillMaxWidth().clickable(role = androidx.compose.ui.semantics.Role.Button) { aboutExpanded = !aboutExpanded }
                    .heightIn(min = PresentationTokens.controlHeight.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Text(stringResource(R.string.about), modifier = Modifier.weight(1f), fontSize = PresentationTokens.typeControl.sp, fontWeight = FontWeight.SemiBold)
                    Text(if (aboutExpanded) "−" else "+")
                }
                if (aboutExpanded) {
                    SuzentTextButton(onClick = model::startDemo, enabled = !model.busy && !model.streaming) {
                        Text(stringResource(R.string.demo_enter), style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
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
    LazyColumn(Modifier.weight(1f).fillMaxWidth().pointerInput(Unit) {
        detectTapGestures(onTap = { keyboard?.hide(); focus.clearFocus() })
    }, state = scroll, reverseLayout = chat.id.isNotEmpty(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceLarge.dp)) {
        item(key = "approvals") { ApprovalCards(model) }
        if (model.streaming || model.liveParts.isNotEmpty()) item(key = "live") {
            // The reversed list follows growth directly; restarting a height tween on
            // each batch keeps clipping the newest line while text is still arriving.
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
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
        if (!expanded && model.attachmentsSupported && model.device?.permissions?.send == true)
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
            if (model.attachmentsSupported && model.device?.permissions?.send == true)
                AttachButton(model, enabled = !model.busy && model.attachments.size < MAX_ATTACHMENTS)
            Box(Modifier.weight(1f)) {
                SuzentTextButton(onClick = { modelsExpanded = true; focus.clearFocus(); keyboard?.hide() },
                    enabled = !model.busy && !model.streaming && chat.models.isNotEmpty() && model.device?.permissions?.send == true) {
                    Text(model.selectedModel ?: chat.model ?: stringResource(R.string.desktop_model),
                        modifier = Modifier.weight(1f, fill = false), maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.MiddleEllipsis,
                        fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(" ⌄", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }

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
    val stopping = model.streaming || chat.running
    val enabled = if (stopping) model.device?.permissions?.stop == true else
        !model.busy && (model.draft.isNotBlank() || model.attachments.isNotEmpty()) && model.device?.permissions?.send == true
    SuzentIconButton(onClick = { if (stopping) model.stop() else model.send() },
        label = stringResource(if (stopping) R.string.stop else R.string.send), enabled = enabled) {
        Box(Modifier.size(36.dp).background(if (stopping) MaterialTheme.colorScheme.error else suzentLink)
            .border(2.dp, MaterialTheme.colorScheme.outline), contentAlignment = androidx.compose.ui.Alignment.Center) {
            androidx.compose.foundation.Canvas(Modifier.size(20.dp)) {
                if (stopping) drawRect(Color.White, topLeft = Offset(size.width * .25f, size.height * .25f), size = Size(size.width * .5f, size.height * .5f))
                else {
                    val path = androidx.compose.ui.graphics.Path().apply {
                        moveTo(size.width * .5f, size.height * .85f); lineTo(size.width * .5f, size.height * .15f)
                        moveTo(size.width * .2f, size.height * .45f); lineTo(size.width * .5f, size.height * .15f); lineTo(size.width * .8f, size.height * .45f)
                    }
                    drawPath(path, Color.White, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2.5.dp.toPx()))
                }
            }
        }
    }
}

@Composable
private fun StartPage(model: MobileModel, chat: Chat, keyboardVisible: Boolean) {
    var projectsExpanded by remember { mutableStateOf(false) }
    var hour by remember { mutableIntStateOf(java.time.LocalTime.now().hour) }
    LaunchedEffect(Unit) { while (true) { hour = java.time.LocalTime.now().hour; kotlinx.coroutines.delay(60000) } }
    val greeting = when { hour < 5 -> R.string.greeting_night; hour < 12 -> R.string.greeting_morning; hour < 17 -> R.string.greeting_build; hour < 21 -> R.string.greeting_evening; else -> R.string.greeting_bed }
    Column(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = if (keyboardVisible) 12.dp else 40.dp),
        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(28.dp)) {
        GreetingCube(engaged = keyboardVisible, modifier = Modifier.size(if (keyboardVisible) 90.dp else 160.dp))
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
        if (model.isDemo) model.demoPrompts.forEach { prompt ->
            SuzentAction(prompt, { model.draft = prompt; model.send() }, enabled = !model.busy && !model.streaming)
        }
    }
}

@Composable
private fun SidebarSectionHeading(label: String, count: Int? = null) {
    // Desktop section headings: 10px extrabold uppercase, 0.16em tracking, muted.
    Row(Modifier.fillMaxWidth().padding(start = 12.dp, top = 12.dp, bottom = 6.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Text(label.uppercase(java.util.Locale.getDefault()), fontWeight = FontWeight.ExtraBold,
            fontSize = PresentationTokens.typeSidebarSection.sp, letterSpacing = 1.6.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
        if (count != null) Text(count.toString(), fontWeight = FontWeight.Bold,
            fontSize = PresentationTokens.typeSidebarSection.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
