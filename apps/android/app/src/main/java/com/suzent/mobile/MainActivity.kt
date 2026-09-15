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
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
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
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    LaunchedEffect(Unit) { if (model.canReconnect && !model.connected) model.connect() }
    LaunchedEffect(model.connected) {
        if (model.connected) { drawer.open(); model.watchNavigation() }
        else { showSettings = false; drawer.close() }
    }
    ModalNavigationDrawer(drawerState = drawer, gesturesEnabled = model.connected, drawerContent = {
        if (model.connected) ModalDrawerSheet(modifier = Modifier.width(320.dp), drawerShape = RectangleShape) {
            Sidebar(model, showSettings,
                close = { scope.launch { drawer.close() } },
                open = { chat -> focus.clearFocus(); model.open(chat); showSettings = false; scope.launch { drawer.close() } },
                create = { projectId -> model.create(projectId); showSettings = false; scope.launch { drawer.close() } },
                settings = { focus.clearFocus(); showSettings = true; scope.launch { drawer.close() } })
        }
    }) {
        Scaffold(topBar = {
            Column(Modifier.statusBarsPadding()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    if (model.connected) {
                        val label = stringResource(R.string.open_sidebar)
                        TextButton(onClick = { focus.clearFocus(); scope.launch { drawer.open() } }, modifier = Modifier.size(44.dp).semantics { contentDescription = label }) { Text("☰") }
                    }
                    Box(Modifier.weight(1f)) { SuzentWordmark() }
                    if (model.connected) TextButton(onClick = { focus.clearFocus(); model.create(); showSettings = false },
                        enabled = !model.busy && !model.streaming && model.device?.permissions?.createChats == true) { Text(stringResource(R.string.new_chat)) }
                }
                HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
            }
        }) { padding ->
            Column(Modifier.fillMaxSize().padding(padding).imePadding()) {
                model.error?.let { message ->
                    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.secondaryContainer).padding(12.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Text(message, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSecondaryContainer)
                        TextButton(onClick = { model.error = null }) { Text(stringResource(R.string.dismiss)) }
                    }
                }
                when {
                    !model.connected && model.canReconnect -> Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
                        Text(stringResource(R.string.reconnect), style = MaterialTheme.typography.titleMedium)
                        if (model.busy) CircularProgressIndicator()
                        else TextButton(onClick = model::connect) { Text(stringResource(R.string.reconnect)) }
                        TextButton(onClick = model::forget, enabled = !model.busy) { Text(stringResource(R.string.forget)) }
                    }
                    !model.connected -> Box(Modifier.padding(horizontal = 16.dp)) { PairingView(model) }
                    showSettings -> SettingsView(model)
                    model.selected != null -> Conversation(model)
                    else -> Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
                        Text(stringResource(R.string.choose_conversation), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(20.dp))
                        SuzentAction(stringResource(R.string.new_chat), { model.create() }, prominent = true,
                            enabled = !model.busy && !model.streaming && model.device?.permissions?.createChats == true)
                    }
                }
            }
        }
    }
}

@Composable
private fun Sidebar(model: MobileModel, settingsSelected: Boolean, close: () -> Unit, open: (Chat) -> Unit, create: (String?) -> Unit, settings: () -> Unit) {
    var search by rememberSaveable { mutableStateOf("") }
    var collapsedProjects by remember { mutableStateOf(setOf<String>()) }
    val projects = remember(model.projects, model.chats) {
        (model.projects + model.chats.mapNotNull { chat -> chat.projectId?.let { Project(it, chat.projectName ?: it) } }).distinctBy { it.id }
    }
    Column(Modifier.fillMaxHeight()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text(stringResource(R.string.chats), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            val label = stringResource(R.string.close_sidebar)
            TextButton(onClick = close, modifier = Modifier.size(44.dp).semantics { contentDescription = label }) { Text("×") }
        }
        OutlinedTextField(search, { search = it }, singleLine = true, placeholder = { Text(stringResource(R.string.search_chats)) }, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp))
        LazyColumn(Modifier.weight(1f).padding(horizontal = 16.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
            projects.forEach { project ->
                item(key = "project:${project.id}") {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        TextButton(onClick = { collapsedProjects = if (project.id in collapsedProjects) collapsedProjects - project.id else collapsedProjects + project.id }, modifier = Modifier.weight(1f)) {
                            Text((if (project.id in collapsedProjects) "▸ " else "▾ ") + project.name, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurface)
                        }
                        val label = stringResource(R.string.new_chat)
                        TextButton(onClick = { create(project.id) }, enabled = !model.busy && !model.streaming && model.device?.permissions?.createChats == true && model.projects.any { it.id == project.id },
                            modifier = Modifier.size(44.dp).semantics { contentDescription = label }) { Text("+") }
                    }
                }
                if (project.id !in collapsedProjects || search.isNotEmpty()) items(model.chats.filter { it.projectId == project.id && it.title.contains(search, ignoreCase = true) }, key = { it.id }) {
                    SidebarChat(it, model.selected?.id == it.id && !settingsSelected, !model.busy, open)
                }
            }
            items(model.chats.filter { it.projectId == null && it.title.contains(search, ignoreCase = true) }, key = { it.id }) {
                SidebarChat(it, model.selected?.id == it.id && !settingsSelected, !model.busy, open)
            }
            if (projects.isEmpty() && model.chats.isEmpty()) item {
                TextButton(onClick = { create(null) }, enabled = !model.busy && !model.streaming && model.device?.permissions?.createChats == true) { Text(stringResource(R.string.new_chat)) }
            }
        }
        HorizontalDivider()
        TextButton(onClick = settings, modifier = Modifier.fillMaxWidth().padding(8.dp)) { Text(stringResource(R.string.settings), modifier = Modifier.fillMaxWidth(), fontWeight = FontWeight.Bold) }
    }
}

@Composable
private fun SidebarChat(chat: Chat, selected: Boolean, enabled: Boolean, open: (Chat) -> Unit) {
    Row(Modifier.fillMaxWidth().background(if (selected) MaterialTheme.colorScheme.onSurface.copy(alpha = 0.08f) else MaterialTheme.colorScheme.surface)
        .clickable(enabled = enabled) { open(chat) }.heightIn(min = 48.dp).padding(12.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Text(chat.title, Modifier.weight(1f), maxLines = 2, fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal)
        if (chat.running) Text("…", color = MaterialTheme.colorScheme.primary)
    }
}

@Composable
private fun SettingsView(model: MobileModel) {
    var accessExpanded by rememberSaveable { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
        Text(stringResource(R.string.settings), style = MaterialTheme.typography.titleLarge)
        Column(Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outlineVariant).padding(16.dp)) {
            TextButton(onClick = { accessExpanded = !accessExpanded }) { Text(stringResource(R.string.access), modifier = Modifier.weight(1f)); Text(if (accessExpanded) "−" else "+") }
            if (accessExpanded) model.device?.let { ClientPermissionsView(it, model.origin) }
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text(stringResource(R.string.enable_node), Modifier.weight(1f))
            Switch(checked = model.nodeEnabled, onCheckedChange = model::toggleNode)
        }
        Text(model.nodeStatus, style = MaterialTheme.typography.bodySmall)
        TextButton(onClick = model::forget, enabled = !model.busy) { Text(stringResource(R.string.forget)) }
        Text(stringResource(R.string.revoke_help), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun ColumnScope.Conversation(model: MobileModel) {
    val chat = model.selected ?: return
    val expanded = WindowInsets.ime.getBottom(LocalDensity.current) > 0
    val keyboard = LocalSoftwareKeyboardController.current
    val focus = LocalFocusManager.current
    val scroll = rememberLazyListState()
    var modelsExpanded by remember { mutableStateOf(false) }
    LaunchedEffect(chat.id) { model.watchApprovals(chat.id) }
    LaunchedEffect(model.sentVersion) {
        if (model.sentVersion > 0) {
            keyboard?.hide(); focus.clearFocus()
            val last = scroll.layoutInfo.totalItemsCount - 1
            if (last >= 0) scroll.animateScrollToItem(last)
        }
    }
    val liveTools = model.liveParts.filter { it.type == "tool" }.map { it.toolCallId }.toSet()
    val messages = remember(chat.messages, liveTools) { presentMessages(chat.messages, liveTools) }
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)) {
        chat.projectName?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        Text(if (chat.id.isEmpty()) stringResource(R.string.new_chat) else chat.title, style = MaterialTheme.typography.titleMedium, maxLines = 1)
    }
    LazyColumn(Modifier.weight(1f).fillMaxWidth().pointerInput(Unit) {
        detectTapGestures(onTap = { keyboard?.hide(); focus.clearFocus() })
    }, state = scroll, contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceLarge.dp)) {
        items(messages) { MessageView(it) }
        if (model.streaming || model.liveParts.isNotEmpty()) item {
            if (model.liveParts.isEmpty()) Text(stringResource(R.string.working), color = MaterialTheme.colorScheme.onSurfaceVariant)
            else ActivityContent(model.liveParts, live = model.streaming)
        }
        item { ApprovalCards(model) }
    }
    Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)
        .border(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline).padding(if (expanded) 12.dp else 6.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.Bottom) {
        BasicTextField(value = model.draft, onValueChange = { model.draft = it }, enabled = !model.busy,
            modifier = Modifier.weight(1f).padding(vertical = 6.dp), minLines = 1, maxLines = if (expanded) 6 else 1,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Default),
            textStyle = MaterialTheme.typography.bodyMedium.copy(color = MaterialTheme.colorScheme.onSurface),
            cursorBrush = androidx.compose.ui.graphics.SolidColor(MaterialTheme.colorScheme.primary),
            decorationBox = { inner -> Box { if (model.draft.isEmpty()) Text(stringResource(R.string.message), color = MaterialTheme.colorScheme.onSurfaceVariant); inner() } })
        if (!expanded) SendAction(model, chat)
        }
        if (expanded) Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) {
                TextButton(onClick = { modelsExpanded = true }, enabled = !model.busy && !model.streaming && chat.models.isNotEmpty() && model.device?.permissions?.send == true) {
                    Text((model.selectedModel ?: chat.model ?: stringResource(R.string.desktop_model)) + " ▾", maxLines = 1, style = MaterialTheme.typography.labelMedium)
                }
                DropdownMenu(expanded = modelsExpanded, onDismissRequest = { modelsExpanded = false }) {
                    DropdownMenuItem(text = { Text(stringResource(R.string.conversation_default)) }, onClick = { model.selectedModel = null; modelsExpanded = false })
                    chat.models.forEach { name -> DropdownMenuItem(text = { Text((if (model.selectedModel == name) "✓ " else "") + name) }, onClick = { model.selectedModel = name; modelsExpanded = false }) }
                }
            }
            SendAction(model, chat)
        }
    }
}

@Composable
private fun SendAction(model: MobileModel, chat: Chat) {
            if (model.streaming || chat.running) SuzentAction(stringResource(R.string.stop), model::stop, prominent = true, enabled = model.device?.permissions?.stop == true, compact = true)
            else SuzentAction(stringResource(R.string.send), model::send, prominent = true,
                enabled = !model.busy && model.draft.isNotBlank() && model.device?.permissions?.send == true, compact = true)
}
