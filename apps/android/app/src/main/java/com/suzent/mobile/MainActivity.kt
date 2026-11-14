package com.suzent.mobile

import android.animation.ValueAnimator
import android.os.Bundle
import androidx.activity.compose.PredictiveBackHandler
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.geometry.Offset
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val model: MobileModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AppPreferences.load(this)
        enableEdgeToEdge()
        setContent {
            AppPreferencesProvider {
                // System bar icons follow the in-app appearance, not only the system one.
                val dark = isSystemInDarkTheme()
                LaunchedEffect(dark) {
                    val style = SystemBarStyle.auto(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT) { dark }
                    enableEdgeToEdge(style, style)
                }
                SuzentTheme { MobileScreen(model) }
            }
        }
    }
    override fun onStart() { super.onStart(); model.setForeground(true) }
    override fun onStop() { model.setForeground(false); super.onStop() }
}

/** Window width at which the chat list and the conversation sit side by side. */
private val WideLayoutWidth = 840.dp

@Composable
private fun MobileScreen(model: MobileModel) {
    var showSettings by rememberSaveable { mutableStateOf(false) }
    var repairScanner by remember { mutableStateOf(false) }
    if (repairScanner) PairingScanner(model) { repairScanner = false }
    var showHome by rememberSaveable { mutableStateOf(true) }
    var mailboxWide by rememberSaveable { mutableStateOf(false) }
    var tab by rememberSaveable { mutableStateOf(HomeTab.CHATS) }
    var desktopsOpen by rememberSaveable { mutableStateOf(false) }
    var searching by rememberSaveable { mutableStateOf(false) }
    val pageState = rememberSaveableStateHolder()
    val focus = LocalFocusManager.current
    LaunchedEffect(Unit) { if (model.canReconnect && !model.connected) model.connect() }
    LaunchedEffect(model.connected, model.isDemo, model.desktops.activeId) {
        showSettings = false
        showHome = true
        desktopsOpen = false
        searching = false
        tab = HomeTab.CHATS
        if (model.connected) model.watchNavigation()
    }
    BoxWithConstraints(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface)
        .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal))) {
        val wide = maxWidth >= WideLayoutWidth
        LaunchedEffect(showHome, showSettings, model.selected?.id, wide) {
            model.regentVisible = (wide || !showHome) && !showSettings && model.selected?.isRegent == true
            model.chatVisible = (wide || !showHome) && !showSettings
        }
        val openChat: (Chat) -> Unit = { chat -> focus.clearFocus(); model.open(chat); showSettings = false; showHome = false }
        val sidebar: @Composable () -> Unit = {
            // On a phone the list is only visible after leaving the chat, so the last-opened row must not stay filled.
            Sidebar(model, showSettings || !wide, tabs = !wide, open = openChat,
                openSearch = if (wide) null else ({ focus.clearFocus(); searching = true }),
                create = { projectId -> focus.clearFocus(); model.create(projectId); showSettings = false; showHome = false },
                settings = { focus.clearFocus(); showSettings = true; showHome = false; desktopsOpen = false })
        }
        val home: @Composable () -> Unit = {
            pageState.SaveableStateProvider("home") {
                Surface(Modifier.fillMaxSize()) {
                    if (wide) Column {
                        TextButton({ mailboxWide = !mailboxWide }) { Text(stringResource(if (mailboxWide) R.string.tab_chats else R.string.mailbox_title) + if (!mailboxWide && model.mailbox.unread > 0) " (${model.mailbox.unread})" else "") }
                        Box(Modifier.weight(1f)) { if (mailboxWide) MailboxView(model, openChat) else sidebar() }
                    }
                    else if (searching) SearchPage(model, openChat, close = { focus.clearFocus(); searching = false })
                    else TabHome(tab, { focus.clearFocus(); tab = it }, model.mailbox.unread) {
                        when (it) {
                            HomeTab.CHATS -> sidebar()
                            HomeTab.INBOX -> MailboxView(model, openChat)
                            HomeTab.SETTINGS -> Column(Modifier.fillMaxSize().statusBarsPadding()) {
                                androidx.activity.compose.BackHandler(enabled = desktopsOpen) { desktopsOpen = false }
                                if (desktopsOpen) DesktopsView(model, back = { desktopsOpen = false })
                                else {
                                    TabTitle(stringResource(R.string.settings))
                                    SettingsView(model, openDesktops = { desktopsOpen = true })
                                }
                            }
                        }
                    }
                }
            }
        }
        val detail: @Composable (Boolean) -> Unit = { compact ->
            DetailPane(model, showSettings, desktopsOpen, { desktopsOpen = it },
                back = if (compact) ({ focus.clearFocus(); showHome = true }) else null,
                newChat = { focus.clearFocus(); model.create(); showSettings = false },
                repair = { model.error = null; model.beginPairing(repairActive = true); repairScanner = true })
        }
        // Back from the results closes search; back from a chat opened there returns to the results.
        androidx.activity.compose.BackHandler(enabled = !wide && searching && showHome) { focus.clearFocus(); searching = false }
        when {
            !model.connected -> detail(false)
            wide -> Row(Modifier.fillMaxSize()) {
                Box(Modifier.width(PresentationTokens.sidebarWidth.dp).fillMaxHeight()) { home() }
                VerticalDivider(thickness = PresentationTokens.borderWidthHeavy.dp, color = MaterialTheme.colorScheme.outline)
                Box(Modifier.weight(1f).fillMaxHeight()) { detail(false) }
            }
            else -> CompactStack(showHome, back = { focus.clearFocus(); showHome = true }, home = home) { detail(true) }
        }
        // A visible conversation hosts the toast above its composer instead, matching iOS.
        val conversationVisible = model.connected && (wide || !showHome) && !showSettings && model.selected != null
        if (!conversationVisible) SuzentErrorHost(model, Modifier.align(Alignment.BottomCenter).navigationBarsPadding().imePadding())
    }
}

/**
 * List → detail push for compact windows. The back gesture scrubs the detail off to the right with
 * the list revealed underneath; releasing commits, cancelling springs back.
 */
@Composable
private fun CompactStack(showHome: Boolean, back: () -> Unit, home: @Composable () -> Unit, detail: @Composable () -> Unit) {
    val motion = remember { ValueAnimator.areAnimatorsEnabled() }
    // 0: detail in front; 1: list in front.
    val reveal = remember { Animatable(if (showHome) 1f else 0f) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(showHome) {
        val target = if (showHome) 1f else 0f
        if (motion) reveal.animateTo(target, tween(280, easing = FastOutSlowInEasing)) else reveal.snapTo(target)
    }
    PredictiveBackHandler(enabled = !showHome) { progress ->
        try {
            progress.collect { event -> if (motion) reveal.snapTo(event.progress) }
            back()
        } catch (cancelled: CancellationException) {
            scope.launch { reveal.animateTo(0f, tween(180)) }
            throw cancelled
        }
    }
    BoxWithConstraints(Modifier.fillMaxSize().clipToBounds()) {
        val width = constraints.maxWidth.toFloat()
        val homeVisible by remember(showHome) { derivedStateOf { showHome || reveal.value > 0f } }
        val detailVisible by remember(showHome) { derivedStateOf { !showHome || reveal.value < 1f } }
        if (homeVisible) Box(Modifier.fillMaxSize().graphicsLayer { translationX = -(1f - reveal.value) * width * .25f }) { home() }
        if (detailVisible) Box(Modifier.fillMaxSize().graphicsLayer { translationX = reveal.value * width }) { detail() }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DetailPane(model: MobileModel, showSettings: Boolean, desktopsOpen: Boolean, openDesktops: (Boolean) -> Unit,
                       back: (() -> Unit)?, newChat: () -> Unit, repair: () -> Unit) {
    val selected = model.selected
    val infoAvailable = model.connected && !showSettings && model.overviewSupported &&
        selected != null && selected.id.isNotEmpty()
    var infoOpen by rememberSaveable { mutableStateOf(false) }
    val wide = back == null
    if (infoOpen && infoAvailable && !wide && selected != null) ModalBottomSheet(onDismissRequest = { infoOpen = false },
        shape = RectangleShape, containerColor = MaterialTheme.colorScheme.surface) {
        ChatInfoPanel(model, selected.id, Modifier.fillMaxWidth())
    }
    Scaffold(topBar = {
        Column(Modifier.statusBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                if (model.connected && back != null) {
                    SuzentIconButton(onClick = back, label = stringResource(R.string.back_to_chats)) {
                        Icon(painterResource(R.drawable.ic_chat_back), contentDescription = null, modifier = Modifier.size(20.dp))
                    }
                }
                Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                    val chat = model.selected
                    if (model.connected && showSettings) {
                        Text(stringResource(R.string.settings), style = MaterialTheme.typography.titleMedium, maxLines = 1)
                    } else if (model.connected && chat != null && chat.id.isNotEmpty()) {
                        if (chat.isRegent) RegentIdentity(working = model.streaming || chat.running, waiting = chat.regent?.waiting ?: 0)
                        else Column(Modifier.padding(horizontal = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            chat.projectName?.let { Text(it, style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                            Text(chat.title, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                        }
                    } else if (!model.connected && model.canReconnect) {
                        Text("SUZENT", modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp),
                            fontSize = 13.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 2.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    } else SuzentWordmark()
                }
                if (infoAvailable) SuzentIconButton(onClick = { infoOpen = !infoOpen }, label = stringResource(R.string.chat_info),
                    modifier = Modifier.semantics { this.selected = infoOpen }) {
                    PanelToggleIcon(infoOpen, bottom = !wide, Modifier.size(22.dp))
                }
                if (model.connected) SuzentIconButton(onClick = newChat, label = stringResource(R.string.new_chat),
                    enabled = !model.busy && model.device?.permissions?.createChats == true) {
                    Icon(painterResource(R.drawable.ic_new_chat), contentDescription = null, modifier = Modifier.size(20.dp))
                }
            }
            if (model.connected || !model.canReconnect) HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
        }
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).imePadding()) {
            when {
                !model.connected && model.canReconnect -> ReconnectView(model, repair)
                !model.connected -> Box(Modifier.padding(horizontal = 16.dp)) { PairingView(model) }
                showSettings && desktopsOpen -> DesktopsView(model, back = { openDesktops(false) })
                showSettings -> SettingsView(model, openDesktops = { openDesktops(true) })
                selected != null && wide && infoOpen && infoAvailable -> Row(Modifier.weight(1f)) {
                    Column(Modifier.weight(1f).fillMaxHeight()) { ProvideSurfaceHandler(surfaceHandler(model, selected)) { Conversation(model) } }
                    ChatInfoColumn(model, selected.id)
                }
                selected != null -> ProvideSurfaceHandler(surfaceHandler(model, selected)) { Conversation(model) }
                else -> Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
                    if (model.busy) CircularProgressIndicator() else Text(stringResource(R.string.select_conversation), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ReconnectView(model: MobileModel, repair: () -> Unit) {
    var helpOpen by remember { mutableStateOf(false) }
    var forgetting by remember { mutableStateOf(false) }
    var scanner by remember { mutableStateOf(false) }
    if (scanner) PairingScanner(model) { scanner = false }
    Column(Modifier.fillMaxSize().padding(horizontal = 24.dp).padding(bottom = 20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.weight(1f))
        Column(verticalArrangement = Arrangement.spacedBy(21.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            ReconnectIndicator(active = model.busy, stage = model.reconnectStage)
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(stringResource(if (model.busy) R.string.connecting_suzent else R.string.reconnect),
                    fontSize = 21.sp, fontWeight = FontWeight.Medium, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                ActiveDesktopLabel(model)
                val status = model.reconnectStatus
                Box(Modifier.fillMaxWidth().heightIn(min = 16.dp), contentAlignment = Alignment.Center) {
                    Text(if (model.busy) status.orEmpty() else "", fontSize = PresentationTokens.typeCaption.sp, fontFamily = FontFamily.Monospace,
                        fontWeight = FontWeight.SemiBold, letterSpacing = 0.8.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                }
            }
            Box(Modifier.heightIn(min = 44.dp)) {
                if (model.busy) {
                    if (model.reconnecting) SuzentTextButton(onClick = model::cancelReconnect) {
                        Text(stringResource(R.string.cancel_reconnect), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                } else SuzentTextButton(onClick = model::connect) {
                    Text(stringResource(R.string.reconnect), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        Spacer(Modifier.weight(1f))
        val others = model.desktops.desktops.filter { it.id != model.desktops.activeId }
        if (others.isNotEmpty()) {
            Text(stringResource(R.string.other_desktops), Modifier.fillMaxWidth().padding(bottom = 4.dp),
                fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Column(Modifier.fillMaxWidth().heightIn(max = 220.dp).verticalScroll(rememberScrollState())) {
                others.forEach { desktop ->
                    key(desktop.id) {
                        // Tappable while the default desktop is still being tried: the switch abandons that attempt.
                        ListItem(leadingContent = { DesktopSquare(desktop.id, 12.dp) },
                            headlineContent = { Text(desktop.name, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                            supportingContent = { Text(displayOrigin(desktop.connection.origin), maxLines = 1, overflow = TextOverflow.Ellipsis) },
                            modifier = Modifier.clickable(enabled = model.reconnecting || !model.busy, role = Role.Button,
                                onClickLabel = stringResource(R.string.switch_to_desktop, desktop.name)) { model.switchDesktop(desktop.id) })
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            SuzentTextButton(onClick = { model.cancelReconnect(); model.error = null; model.beginPairing(repairActive = false); scanner = true },
                enabled = model.reconnecting || !model.busy) {
                Text(stringResource(R.string.pair_another_desktop), fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            SuzentTextButton(onClick = { helpOpen = true }) {
                Text(stringResource(R.string.connection_help), fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
    if (helpOpen) ModalBottomSheet(onDismissRequest = { helpOpen = false }, shape = RectangleShape,
        containerColor = MaterialTheme.colorScheme.surface) {
        Column(Modifier.fillMaxWidth().padding(bottom = PresentationTokens.spacePage.dp)) {
            Text(stringResource(R.string.connection_help), Modifier.padding(horizontal = 16.dp),
                style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Text(stringResource(R.string.connection_help_detail), Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            SettingsRow(stringResource(R.string.pair_again), { helpOpen = false; repair() }, enabled = !model.busy && !model.streaming)
            SettingsRow(stringResource(R.string.forget), { helpOpen = false; forgetting = true }, enabled = !model.busy, danger = true)
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            SettingsRow(stringResource(R.string.cancel_reconnect), { helpOpen = false })
        }
    }
    if (forgetting) ForgetConnectionDialog(model) { forgetting = false }
}

@Composable
private fun ForgetConnectionDialog(model: MobileModel, dismiss: () -> Unit) {
    AlertDialog(onDismissRequest = dismiss, title = { Text(stringResource(R.string.forget)) },
        text = { Text(stringResource(R.string.forget_warning)) },
        confirmButton = { TextButton(onClick = { dismiss(); model.forget() }, enabled = !model.busy) {
            Text(stringResource(R.string.forget), color = MaterialTheme.colorScheme.error)
        } },
        dismissButton = { TextButton(onClick = dismiss) { Text(stringResource(android.R.string.cancel)) } })
}

@Composable
private fun SearchPage(model: MobileModel, open: (Chat) -> Unit, close: () -> Unit) {
    var search by rememberSaveable { mutableStateOf("") }
    val term = search.trim()
    val query = ChatPageQuery("search", term)
    var expandedAgents by remember { mutableStateOf(setOf<String>()) }
    val listState = rememberLazyListState()
    val loaded = query in model.chatPages
    var shownTop by rememberSaveable(term) { mutableStateOf(false) }
    val focusRequester = remember { androidx.compose.ui.focus.FocusRequester() }
    // Only on the way in: coming back from a result should not raise the keyboard again.
    LaunchedEffect(Unit) { if (search.isEmpty()) focusRequester.requestFocus() }
    // Results arrive above the footer, and the list would otherwise stay anchored on it at the bottom.
    // Once per term, so coming back from a result keeps its scroll position.
    LaunchedEffect(term, loaded) {
        if (loaded && !shownTop) { listState.scrollToItem(0); shownTop = true }
    }
    LaunchedEffect(term, model.navigationVersion) {
        if (term.isNotEmpty()) { kotlinx.coroutines.delay(300); model.loadPage(query) }
    }
    val focus = LocalFocusManager.current
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface).statusBarsPadding().navigationBarsPadding().imePadding()) {
        Row(Modifier.padding(start = 16.dp, end = 8.dp, top = 8.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(value = search, onValueChange = { search = it },
                placeholder = { Text(stringResource(R.string.search_chats)) },
                leadingIcon = { Icon(painterResource(R.drawable.ic_search), contentDescription = null, modifier = Modifier.size(20.dp)) },
                trailingIcon = if (search.isEmpty()) null else ({
                    IconButton(onClick = { search = ""; focusRequester.requestFocus() }) {
                        Icon(painterResource(R.drawable.ic_close), contentDescription = stringResource(R.string.clear_search), modifier = Modifier.size(18.dp))
                    }
                }),
                singleLine = true, shape = RectangleShape,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = androidx.compose.foundation.text.KeyboardActions(onSearch = { focus.clearFocus() }),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color.Transparent, unfocusedBorderColor = Color.Transparent,
                    focusedContainerColor = MaterialTheme.colorScheme.onSurface.copy(alpha = .04f),
                    unfocusedContainerColor = MaterialTheme.colorScheme.onSurface.copy(alpha = .04f)),
                modifier = Modifier.weight(1f).focusRequester(focusRequester))
            TextButton(onClick = close) { Text(stringResource(android.R.string.cancel), color = MaterialTheme.colorScheme.onSurface) }
        }
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), state = listState, contentPadding = PaddingValues(vertical = 12.dp)) {
            if (term.isEmpty()) item(key = "search-hint") {
                Text(stringResource(R.string.search_hint), Modifier.padding(vertical = 24.dp),
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                val results = sidebarChats(model.pageChats(query), term, expandedAgents)
                items(results, key = { "search:${it.chat.id}" }) {
                    SidebarEntry(it, false, model, { chat -> focus.clearFocus(); open(chat) }, it.chat.id in expandedAgents) {
                        expandedAgents = if (it.chat.id in expandedAgents) expandedAgents - it.chat.id else expandedAgents + it.chat.id
                    }
                }
                item(key = "search-more") { ChatPageFooter(model, query) }
                if (results.isEmpty() && query in model.chatPages) item(key = "search-empty") {
                    Text(stringResource(R.string.sidebar_no_results), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun Sidebar(model: MobileModel, hideSelection: Boolean, tabs: Boolean, open: (Chat) -> Unit, create: (String?) -> Unit, settings: () -> Unit,
                    openSearch: (() -> Unit)? = null) {
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
    var scheduledExpanded by rememberSaveable { mutableStateOf(false) }
    var listMode by rememberSaveable { mutableStateOf(HomeListMode.RECENT) }
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
    val searchQuery = ChatPageQuery("search", search.trim())
    val recentRows = sidebarChats(model.pageChats(ChatPageQuery()), "", expandedAgents)
    val pinnedRows = sidebarChats(model.pageChats(ChatPageQuery("pinned")), "", expandedAgents)
    LaunchedEffect(search, model.navigationVersion) {
        if (search.isNotEmpty()) { kotlinx.coroutines.delay(300); model.loadPage(searchQuery) }
    }
    LaunchedEffect(expandedProject, model.navigationVersion) { expandedProject?.let { model.loadPage(ChatPageQuery("project", it)) } }
    // The recent page is newest-first (updated_at desc), so a project's earliest chat index there
    // is its latest activity. Mirrors the desktop sidebar's sortedProjects ordering without adding
    // a timestamp to the mobile payload. model.chats is not ranked: opening a project appends its
    // page there, which would reorder the projects on every expand.
    val recentChats = model.pageChats(ChatPageQuery())
    val projects = remember(model.projects, model.chats, recentChats) {
        val merged = (model.projects + model.chats.filterNot { it.isRegent }.mapNotNull { chat -> chat.projectId?.let { Project(it, chat.projectName ?: it) } }).distinctBy { it.id }
        val serverOrder = merged.withIndex().associate { (index, project) -> project.id to index }
        val activity = mutableMapOf<String, Int>()
        recentChats.forEachIndexed { index, chat ->
            val id = chat.projectId ?: return@forEachIndexed
            if (id in serverOrder && id !in activity) activity[id] = index
        }
        merged.sortedWith(compareBy({ activity[it.id] ?: Int.MAX_VALUE }, { serverOrder.getValue(it.id) }))
    }
    val visibleProjects = if (search.isEmpty() && listMode == HomeListMode.PROJECTS) projects else emptyList()
    val scheduledGroups = scheduledSidebarGroups(model.chats, model.scheduledTasks, search, expandedAgents)
    // Matches the desktop automation preview: five rows, then View all.
    val scheduledPreview = 5
    val visibleScheduledGroups = if (showAllScheduled || search.isNotEmpty()) scheduledGroups else scheduledGroups.take(scheduledPreview)
    val scope = rememberCoroutineScope()
    var refreshing by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxHeight().statusBarsPadding().imePadding()) {
        // The wordmark fills the row to stay centred, so the settings button is layered over its end.
        Box(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), contentAlignment = Alignment.CenterEnd) {
            // Left-aligned beside the phone's search and new icons so it never crowds them.
            SuzentWordmark(leading = openSearch != null)
            if (!tabs) IconButton(onClick = settings) { Icon(painterResource(R.drawable.ic_settings), contentDescription = stringResource(R.string.settings), modifier = Modifier.size(24.dp)) }
            // Phones search on their own page, so results never share the screen with the home list.
            if (openSearch != null) Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = openSearch) {
                    Icon(painterResource(R.drawable.ic_search), contentDescription = stringResource(R.string.search_chats), modifier = Modifier.size(24.dp))
                }
                IconButton(onClick = { create(null) }, enabled = !model.busy && model.device?.permissions?.createChats == true) {
                    Icon(painterResource(R.drawable.ic_new_chat), contentDescription = stringResource(R.string.new_chat), modifier = Modifier.size(24.dp))
                }
            }
        }
        // Under the phone's left-aligned wordmark; centred under the tablet's centred one.
        ActiveDesktopLabel(model, if (openSearch != null) Modifier.padding(horizontal = 16.dp) else Modifier.align(Alignment.CenterHorizontally))
        model.chats.firstOrNull { it.isRegent }?.let { regent ->
            val selected = model.selected?.isRegent == true && !hideSelection
            val regentInteraction = remember { MutableInteractionSource() }
            val regentPressed by regentInteraction.collectIsPressedAsState()
            Row(Modifier.padding(horizontal = 16.dp).fillMaxWidth()
                .clickable(interactionSource = regentInteraction, indication = LocalIndication.current,
                    enabled = !model.busy, role = Role.Button) { open(regent) }.padding(horizontal = 4.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.weight(1f)) {
                    RegentIdentity(working = regent.running || (model.selected?.isRegent == true && model.streaming),
                        waiting = regent.regent?.waiting ?: 0, unread = if (selected) 0 else regent.regent?.unread ?: 0,
                        lastMessageAt = regent.regent?.lastMessageAt, expanded = false, coronation = regentPressed)
                }
                SuzentChevron(false, Modifier.padding(start = 8.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        HorizontalDivider(Modifier.padding(horizontal = 16.dp), color = MaterialTheme.colorScheme.onSurface.copy(alpha = .08f))
        if (openSearch == null) Button(onClick = { create(null) },
            enabled = !model.busy && model.device?.permissions?.createChats == true,
            shape = RectangleShape,
            colors = ButtonDefaults.buttonColors(containerColor = suzentYellow(), contentColor = Color.Black),
            modifier = Modifier.padding(horizontal = 16.dp).padding(top = 12.dp).fillMaxWidth().heightIn(min = 48.dp)) {
            Icon(painterResource(R.drawable.ic_new_chat), contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(10.dp))
            Text(stringResource(R.string.new_chat), fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        }
        if (openSearch == null) OutlinedTextField(value = search, onValueChange = { search = it },
            placeholder = { Text(stringResource(R.string.search_chats)) },
            singleLine = true, shape = RectangleShape,
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Color.Transparent, unfocusedBorderColor = Color.Transparent,
                focusedContainerColor = MaterialTheme.colorScheme.onSurface.copy(alpha = .04f),
                unfocusedContainerColor = MaterialTheme.colorScheme.onSurface.copy(alpha = .04f)),
            modifier = Modifier.padding(horizontal = 16.dp).padding(top = 12.dp).fillMaxWidth())
        if (search.isEmpty()) HomeListPicker(listMode, { listMode = it }, Modifier.padding(horizontal = 16.dp).padding(top = 12.dp))
        PullToRefreshBox(isRefreshing = refreshing, modifier = Modifier.weight(1f).fillMaxWidth(), onRefresh = {
            refreshing = true
            scope.launch { try { model.refresh().join() } finally { refreshing = false } }
        }) {
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), state = listState, contentPadding = PaddingValues(vertical = 12.dp)) {
            if (search.isNotEmpty()) {
                item(key = "search-heading") { SidebarSectionHeading(stringResource(R.string.search_results)) }
                val results = sidebarChats(model.pageChats(searchQuery), search, expandedAgents)
                items(results, key = { "search:${it.chat.id}" }) {
                    SidebarEntry(it, model.selected?.id == it.chat.id && !hideSelection, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
                }
                item(key = "search-more") { ChatPageFooter(model, searchQuery) }
                if (results.isEmpty() && searchQuery in model.chatPages) item(key = "search-empty") {
                    Text(stringResource(R.string.sidebar_no_results), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else if (listMode == HomeListMode.RECENT) {
                if (pinnedRows.isNotEmpty()) {
                    item(key = "pinned-heading") { SidebarSectionHeading(stringResource(R.string.pinned_chats)) }
                    items(pinnedRows, key = { "pinned:${it.chat.id}" }) {
                        SidebarEntry(it, model.selected?.id == it.chat.id && !hideSelection, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
                    }
                    item(key = "pinned-more") { ChatPageFooter(model, ChatPageQuery("pinned")) }
                    if (recentRows.isNotEmpty()) item(key = "recent-heading") { SidebarSectionHeading(stringResource(R.string.recent_chats)) }
                }
                items(recentRows, key = { "recent:${it.chat.id}" }) {
                    SidebarEntry(it, model.selected?.id == it.chat.id && !hideSelection, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
                }
                item(key = "recent-more") { ChatPageFooter(model, ChatPageQuery()) }
            } else if (projects.isEmpty()) item(key = "projects-empty") {
                Text(stringResource(R.string.sidebar_no_projects), modifier = Modifier.padding(vertical = 24.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            visibleProjects.forEach { project ->
                val projectRows = sidebarChats(model.pageChats(ChatPageQuery("project", project.id)), "", expandedAgents)
                val projectOpen = expandedProject == project.id
                val isOpen = projectOpen || search.isNotEmpty()
                item(key = "project:${project.id}") {
                    val projectInteraction = remember { MutableInteractionSource() }
                    val projectPressed by projectInteraction.collectIsPressedAsState()
                    Row(Modifier.fillMaxWidth()
                        .background(if (projectPressed) MaterialTheme.colorScheme.onSurface.copy(alpha = PressedAlpha) else Color.Transparent)
                        .clickable(interactionSource = projectInteraction, indication = null,
                            role = Role.Button) { expandedProject = if (projectOpen) null else project.id }
                        .heightIn(min = 44.dp)
                        .padding(horizontal = 12.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Icon(painterResource(R.drawable.ic_chat_folder), null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(10.dp))
                        Text(project.name, fontWeight = if (!isOpen && project.unread) FontWeight.ExtraBold else FontWeight.Medium,
                            fontSize = PresentationTokens.typeCaption.sp, modifier = Modifier.weight(1f), color = MaterialTheme.colorScheme.onSurface)
                        if (!isOpen && (project.running || projectRows.any { it.chat.running })) Box(Modifier.padding(end = 8.dp)) { StreamingPulse() }
                        Text("${project.chatCount ?: projectRows.size}", fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        SuzentChevron(isOpen, Modifier.padding(start = 12.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                if (isOpen) items(projectRows, key = { "project:${project.id}:${it.chat.id}" }) {
                    SidebarEntry(it, model.selected?.id == it.chat.id && !hideSelection, model, open, it.chat.id in expandedAgents) { toggleAgents(it.chat.id) }
                }
                if (isOpen) item(key = "project-more:${project.id}") { ChatPageFooter(model, ChatPageQuery("project", project.id)) }
            }
            if (search.isEmpty() && listMode == HomeListMode.RECENT && recentRows.isEmpty() && pinnedRows.isEmpty()) item(key = "empty") {
                Text(stringResource(R.string.sidebar_empty), modifier = Modifier.padding(vertical = 24.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (scheduledGroups.isNotEmpty() && !tabs && search.isNotEmpty()) {
                item(key = "scheduled-heading") {
                    SuzentTextButton(onClick = { scheduledExpanded = !scheduledExpanded }, modifier = Modifier.fillMaxWidth()) {
                        Icon(painterResource(R.drawable.ic_clock), contentDescription = null, modifier = Modifier.padding(end = 10.dp).size(18.dp))
                        Text(stringResource(R.string.scheduled_tasks), modifier = Modifier.weight(1f), fontWeight = FontWeight.Medium)
                        Text("${scheduledGroups.size}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        SuzentChevron(scheduledExpanded || search.isNotEmpty(), Modifier.padding(start = 12.dp))
                    }
                }
                items(if (scheduledExpanded || search.isNotEmpty()) visibleScheduledGroups else emptyList(), key = { it.id }) { group ->
                    Column {
                        val task = group.task
                        val root = group.root
                        if (task != null) ScheduledTaskRow(task, model, !hideSelection && model.selected?.id == task.chatId,
                            root?.childCount ?: 0, task.chatId in expandedAgents, { task.chatId?.let(::toggleAgents) }) {
                            task.chatId?.let { id -> open(model.chats.firstOrNull { it.id == id } ?: Chat(id, task.name, task.running, emptyList())) }
                        }
                        else if (root != null) SidebarEntry(root, model.selected?.id == root.chat.id && !hideSelection,
                            model, open, root.chat.id in expandedAgents) { toggleAgents(root.chat.id) }
                        group.children.forEach { entry ->
                            SidebarEntry(entry, model.selected?.id == entry.chat.id && !hideSelection, model, open, false) {}
                        }
                    }
                }
                if (scheduledExpanded && search.isEmpty() && scheduledGroups.size > scheduledPreview) {
                    item(key = "scheduled-view-all") {
                        SuzentTextButton(onClick = { showAllScheduled = !showAllScheduled }, modifier = Modifier.fillMaxWidth()) {
                            Text(stringResource(if (showAllScheduled) R.string.task_show_fewer else R.string.task_view_all, scheduledGroups.size),
                                fontSize = PresentationTokens.typeCaption.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
        }
        if (!tabs) Spacer(Modifier.navigationBarsPadding())
    }
}

@Composable
private fun ChatPageFooter(model: MobileModel, query: ChatPageQuery) {
    val scope = rememberCoroutineScope()
    if (query in model.loadingPages) {
        Box(Modifier.fillMaxWidth().height(44.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
        }
    } else if (model.chatPages[query]?.nextOffset != null || query !in model.chatPages) {
        SuzentTextButton(onClick = { scope.launch { model.loadPage(query, more = query in model.chatPages) } }, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.load_more_chats), fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
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
            role = Role.Button, onClick = toggle)
        .semantics(mergeDescendants = true) { contentDescription = label },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(stringResource(R.string.subagent_count, childCount), fontSize = PresentationTokens.typeSidebarSection.sp,
            lineHeight = 14.sp, fontWeight = FontWeight.Medium, color = color, maxLines = 1)
        SuzentChevron(expanded, size = 12.dp, tint = color)
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
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(task.name, fontSize = PresentationTokens.typeCaption.sp, fontWeight = FontWeight.Medium,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            val status = when {
                !task.active -> if (task.unresolvedError) stringResource(R.string.task_paused_failed) else stringResource(R.string.task_paused)
                task.unresolvedError -> stringResource(R.string.task_failed)
                task.nextRunAt != null -> stringResource(R.string.task_next_run, formattedTimestamp(task.nextRunAt))
                else -> stringResource(R.string.task_active)
            }
            Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (task.running) Box(Modifier.size(8.dp).background(suzentLink))
                Text(status, fontSize = PresentationTokens.typeSidebarSection.sp, fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (childCount > 0) {
                    Text("·", fontSize = PresentationTokens.typeSidebarSection.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    SidebarFoldControl(childCount, expanded, toggle)
                }
            }
            if (task.chatId == null) Text(stringResource(R.string.task_no_conversation), fontSize = PresentationTokens.typeCaption.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        val activity = (if (task.failureHandled()) task.chatUpdatedAt else task.lastRunAt)?.let { formattedTimestamp(it) }
            ?: stringResource(R.string.task_not_yet)
        Text(activity,
            fontSize = PresentationTokens.typeSidebarSection.sp, fontWeight = FontWeight.Medium,
            style = androidx.compose.ui.text.TextStyle(fontFeatureSettings = "tnum"),
            color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, modifier = Modifier.padding(start = 8.dp))
    }
}

@Composable
private fun SidebarChat(chat: Chat, selected: Boolean, model: MobileModel, open: (Chat) -> Unit,
                        childCount: Int, expanded: Boolean, toggle: () -> Unit, nested: Boolean) {
    var menu by remember { mutableStateOf(false) }
    var menuAnchor by remember { mutableStateOf<Offset?>(null) }
    var pressAt by remember { mutableLongStateOf(0L) }
    var moving by remember { mutableStateOf(false) }
    var renaming by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf(false) }
    var title by remember { mutableStateOf("") }
    val outline = MaterialTheme.colorScheme.outline
    val interaction = remember(chat.id) { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val foreground = if (pressed) Color.Black else MaterialTheme.colorScheme.onSurface
    val selection = suzentSelection
    val view = LocalView.current
    val scope = rememberCoroutineScope()
    val canManage = model.device?.permissions?.manageChats == true
    val swipe = rememberSwipeToDismissBoxState()
    fun togglePin() = model.manageChat(chat, if (chat.pinned) "unpin" else "pin")
    // A tick as the swipe crosses the action threshold, the way a full swipe arms on iOS.
    LaunchedEffect(swipe) {
        snapshotFlow { swipe.targetValue }.collect { if (it != SwipeToDismissBoxValue.Settled) view.suzentHaptic(SuzentHaptic.Light) }
    }
    Box {
    // Swipes never remove the row: they trigger the action, then the row springs back.
    SwipeToDismissBox(swipe, backgroundContent = {
        val direction = swipe.dismissDirection
        val delete = direction == SwipeToDismissBoxValue.EndToStart
        Row(Modifier.fillMaxSize().background(when (direction) {
            SwipeToDismissBoxValue.StartToEnd -> if (chat.pinned) selection else suzentYellow()
            SwipeToDismissBoxValue.EndToStart -> MaterialTheme.colorScheme.error
            SwipeToDismissBoxValue.Settled -> Color.Transparent
        }).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = if (delete) Arrangement.End else Arrangement.Start) {
            if (direction != SwipeToDismissBoxValue.Settled) Icon(painterResource(when {
                delete -> R.drawable.ic_chat_delete
                chat.pinned -> R.drawable.ic_chat_unpin
                else -> R.drawable.ic_chat_pin
            }), contentDescription = null, modifier = Modifier.size(20.dp), tint = when {
                delete -> MaterialTheme.colorScheme.onError
                chat.pinned -> MaterialTheme.colorScheme.onSurface
                else -> Color.Black
            })
        }
    }, enableDismissFromStartToEnd = canManage && !chat.running && !model.busy,
        enableDismissFromEndToStart = canManage && !chat.running && !model.busy,
        onDismiss = { value ->
            if (value == SwipeToDismissBoxValue.StartToEnd) { view.suzentHaptic(SuzentHaptic.Confirm); togglePin() }
            if (value == SwipeToDismissBoxValue.EndToStart) { view.suzentHaptic(SuzentHaptic.Reject); deleting = true }
            scope.launch { swipe.reset() }
        }) {
    Row(Modifier.fillMaxWidth().background(if (pressed) suzentYellow() else if (selected) selection else MaterialTheme.colorScheme.surface)
        .recordPressInWindow {
            menuAnchor = it
            pressAt = android.os.SystemClock.uptimeMillis()
        }
        .combinedClickable(interactionSource = interaction, indication = null, enabled = !model.busy,
            onLongClickLabel = stringResource(R.string.conversation_actions),
            onLongClick = {
                // TalkBack has no finger. A press older than the long-press window anchors to the row.
                if (android.os.SystemClock.uptimeMillis() - pressAt > 1_500L) menuAnchor = null
                view.suzentHaptic(SuzentHaptic.LongPress)
                moving = false
                menu = true
            }, onClick = { open(chat) })
        .heightIn(min = 44.dp).padding(start = if (nested) 32.dp else 12.dp, end = 12.dp,
            top = PresentationTokens.spaceRow.dp, bottom = PresentationTokens.spaceRow.dp),
        verticalAlignment = Alignment.CenterVertically) {
        if (chat.pinned) Icon(painterResource(R.drawable.ic_chat_pin), null, tint = foreground, modifier = Modifier.padding(end = 6.dp).size(12.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            val unread = chat.unread > 0 && !(model.chatVisible && chat.id == model.selected?.id)
            Text(chat.title, color = foreground, fontSize = PresentationTokens.typeCaption.sp, lineHeight = 18.sp,
                fontWeight = if (unread) FontWeight.ExtraBold else FontWeight.Medium, maxLines = 1,
                overflow = TextOverflow.Ellipsis)
            val muted = if (pressed) Color.Black else MaterialTheme.colorScheme.onSurfaceVariant
            val meta = when {
                chat.isSubagent && !nested -> model.chats.firstOrNull { it.id == chat.parentChatId }
                    ?.let { stringResource(R.string.subagent_of, it.title) } ?: stringResource(R.string.subagent)
                chat.isScheduled -> stringResource(R.string.scheduled_task)
                else -> chat.projectName
            }
            if (meta != null || childCount > 0) Row(Modifier.heightIn(min = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                if (meta != null) Text(meta, fontSize = PresentationTokens.typeSidebarSection.sp, lineHeight = 14.sp,
                    fontWeight = FontWeight.Medium, color = muted,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (meta != null && childCount > 0) Text(" · ", fontSize = PresentationTokens.typeSidebarSection.sp,
                    lineHeight = 14.sp, color = muted)
                if (childCount > 0) SidebarFoldControl(childCount, expanded, toggle, muted)
            }
        }
        if (chat.running) Box(Modifier.padding(start = 8.dp)) { StreamingPulse() }
    }
    }
    SuzentMenu(expanded = menu, onDismissRequest = { menu = false }, anchorInWindow = menuAnchor) {
        if (!canManage) {
            Text(stringResource(R.string.manage_permission_hint), modifier = Modifier.padding(16.dp), fontSize = 13.sp)
        } else if (moving) {
            SuzentMenuItem(stringResource(R.string.move_to_project), R.drawable.ic_chat_back) { moving = false }
            SuzentMenuDivider()
            model.projects.forEach { project ->
                val current = project.id == chat.projectId
                SuzentMenuItem(project.name, R.drawable.ic_chat_folder,
                    enabled = !current && !model.busy, selected = current) {
                    menu = false; model.manageChat(chat, "move", project.id)
                }
            }
        } else {
            SuzentMenuItem(stringResource(if (chat.pinned) R.string.unpin_chat else R.string.pin_chat), R.drawable.ic_chat_pin) { menu = false; togglePin() }
            SuzentMenuItem(stringResource(R.string.rename_chat), R.drawable.ic_chat_rename) { menu = false; title = chat.title; renaming = true }
            SuzentMenuItem(stringResource(R.string.move_to_project), R.drawable.ic_chat_folder, enabled = !chat.running && model.projects.isNotEmpty()) { moving = true }
            SuzentMenuDivider()
            SuzentMenuItem(stringResource(R.string.delete_chat), R.drawable.ic_chat_delete, enabled = !chat.running, danger = true) { menu = false; deleting = true }
        }
    }
    }
    if (renaming) SuzentInputSheet(title = stringResource(R.string.rename_chat), value = title, onValueChange = { title = it },
        placeholder = stringResource(R.string.conversation_title), saveLabel = stringResource(R.string.save_chat),
        saveEnabled = title.trim().isNotEmpty() && title.length <= 200 && !model.busy,
        dismiss = { renaming = false }, save = { renaming = false; model.manageChat(chat, "rename", title.trim()) })
    if (deleting) AlertDialog(onDismissRequest = { deleting = false }, title = { Text(stringResource(R.string.delete_chat)) },
        text = { Text(stringResource(R.string.delete_chat_warning)) },
        confirmButton = { TextButton(onClick = { deleting = false; model.manageChat(chat, "delete") }, enabled = !model.busy) {
            Text(stringResource(R.string.delete_chat), color = MaterialTheme.colorScheme.error)
        } },
        dismissButton = { TextButton(onClick = { deleting = false }) { Text(stringResource(android.R.string.cancel)) } })
}

@Composable
private fun SettingsView(model: MobileModel, openDesktops: () -> Unit) {
    var repairScanner by remember { mutableStateOf(false) }
    if (repairScanner) PairingScanner(model) { repairScanner = false }
    var accessExpanded by rememberSaveable { mutableStateOf(false) }
    var forgetting by remember { mutableStateOf(false) }
    if (forgetting) ForgetConnectionDialog(model) { forgetting = false }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = PresentationTokens.spaceLarge.dp)) {
        if (model.isDemo) {
            SettingsSection(stringResource(R.string.demo_section), divider = false)
            SettingsRow(stringResource(R.string.demo_reset), model::resetDemo, enabled = !model.busy)
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            SettingsRow(stringResource(R.string.demo_exit), model::exitDemo, enabled = !model.busy)
            SettingsFooter(stringResource(R.string.demo_intro))
            SettingsFooter(stringResource(R.string.demo_limits))
        } else {
            SettingsSection(stringResource(R.string.connection_section), divider = false)
            model.desktops.active?.let { desktop ->
                val dark = isSystemInDarkTheme()
                ListItem(leadingContent = {
                    // The same computer mark as the home screen's desktop line; colour swatches stay in the desktops list.
                    Box(Modifier.size(40.dp).background(Color(if (dark) PresentationTokens.code_header_dark else PresentationTokens.code_bg))
                        .border(1.dp, MaterialTheme.colorScheme.outlineVariant), contentAlignment = Alignment.Center) {
                        Icon(painterResource(R.drawable.ic_desktop), contentDescription = null, modifier = Modifier.size(20.dp))
                    }
                },
                    headlineContent = { Text(desktop.name, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    supportingContent = { Text(stringResource(R.string.desktop_connected, displayOrigin(model.origin)), maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    trailingContent = { Row(verticalAlignment = Alignment.CenterVertically) {
                        val count = model.desktops.desktops.size
                        if (count > 1) Text(pluralStringResource(R.plurals.desktop_count, count, count),
                            fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Icon(painterResource(R.drawable.ic_chevron_right), contentDescription = null, modifier = Modifier.padding(start = 8.dp).size(16.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    } },
                    modifier = Modifier.clickable(role = Role.Button, onClickLabel = stringResource(R.string.desktops), onClick = openDesktops))
            }
            // Everything here applies to the connected desktop only, so it lives in one section.
            SettingsSection(stringResource(R.string.this_desktop))
            ListItem(headlineContent = { Text(stringResource(R.string.permissions), fontWeight = FontWeight.SemiBold) },
                trailingContent = { SuzentChevron(accessExpanded, tint = MaterialTheme.colorScheme.onSurfaceVariant) },
                modifier = Modifier.clickable(role = Role.Button, onClickLabel = stringResource(R.string.permissions)) { accessExpanded = !accessExpanded })
            if (accessExpanded) model.device?.let {
                Box(Modifier.padding(horizontal = PresentationTokens.spacePage.dp, vertical = PresentationTokens.spaceSmall.dp)) { ClientPermissionsView(it, model.origin) }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            ListItem(headlineContent = { Text(stringResource(R.string.enable_node), fontWeight = FontWeight.SemiBold) },
                supportingContent = if (model.nodeEnabled) { { Text(model.nodeStatus) } } else null,
                trailingContent = { Switch(checked = model.nodeEnabled, onCheckedChange = null) },
                modifier = Modifier.toggleable(value = model.nodeEnabled, role = Role.Switch, onValueChange = model::toggleNode))
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            SettingsRow(stringResource(R.string.pair_again), { model.error = null; model.beginPairing(repairActive = true); repairScanner = true }, enabled = !model.busy && !model.streaming)
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            SettingsRow(stringResource(R.string.forget_this_desktop), { forgetting = true }, enabled = !model.busy, danger = true)
            SettingsFooter(stringResource(R.string.revoke_help))
        }
        PreferencesSection()
        SettingsSection(stringResource(R.string.about))
        if (!model.isDemo) {
            SettingsRow(stringResource(R.string.demo_enter), model::startDemo, enabled = !model.busy && !model.streaming)
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        }
        val uriHandler = LocalUriHandler.current
        SettingsRow(stringResource(R.string.privacy_policy), { uriHandler.openUri(PRIVACY_POLICY_URL) })
    }
}

@Composable
private fun PreferencesSection() {
    val context = LocalContext.current
    var picking by remember { mutableStateOf<String?>(null) }
    var language by remember { mutableStateOf(AppPreferences.language(context)) }
    val appearanceLabels = mapOf(AppearancePreference.SYSTEM to R.string.match_system, AppearancePreference.LIGHT to R.string.appearance_light,
        AppearancePreference.DARK to R.string.appearance_dark).mapValues { stringResource(it.value) }
    val textSizeLabels = mapOf(TextSizePreference.SYSTEM to R.string.match_system, TextSizePreference.SMALL to R.string.text_size_small,
        TextSizePreference.LARGE to R.string.text_size_large, TextSizePreference.EXTRA_LARGE to R.string.text_size_extra_large)
        .mapValues { stringResource(it.value) }
    // Language names stay in their own language so they can be found from either one.
    val languageLabels = mapOf(LanguagePreference.SYSTEM to stringResource(R.string.match_system),
        LanguagePreference.ENGLISH to "English", LanguagePreference.CHINESE to "简体中文")
    SettingsSection(stringResource(R.string.preferences))
    PreferenceRow(stringResource(R.string.appearance), appearanceLabels.getValue(AppPreferences.appearance)) { picking = "appearance" }
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
    PreferenceRow(stringResource(R.string.text_size), textSizeLabels.getValue(AppPreferences.textSize)) { picking = "text" }
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
    ListItem(headlineContent = { Text(stringResource(R.string.haptics), fontWeight = FontWeight.SemiBold) },
        trailingContent = { Switch(checked = AppPreferences.haptics, onCheckedChange = null) },
        modifier = Modifier.toggleable(value = AppPreferences.haptics, role = Role.Switch, onValueChange = { AppPreferences.haptics = it }))
    if (AppPreferences.supportsLanguage) {
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        PreferenceRow(stringResource(R.string.language), languageLabels.getValue(language)) { picking = "language" }
    }
    SettingsFooter(stringResource(R.string.preferences_footer))
    when (picking) {
        "appearance" -> SuzentSelectionPanel(stringResource(R.string.appearance), appearanceLabels.map { it.key.name to it.value },
            AppPreferences.appearance.name, dismiss = { picking = null }) { picked ->
            AppPreferences.appearance = AppearancePreference.valueOf(picked); picking = null
        }
        "text" -> SuzentSelectionPanel(stringResource(R.string.text_size), textSizeLabels.map { it.key.name to it.value },
            AppPreferences.textSize.name, dismiss = { picking = null }) { picked ->
            AppPreferences.textSize = TextSizePreference.valueOf(picked); picking = null
        }
        "language" -> SuzentSelectionPanel(stringResource(R.string.language), languageLabels.map { it.key.name to it.value },
            language.name, dismiss = { picking = null }) { picked ->
            // The platform recreates the activity in the new language.
            picking = null; language = LanguagePreference.valueOf(picked); AppPreferences.setLanguage(context, language)
        }
    }
}

@Composable
private fun PreferenceRow(label: String, value: String, onClick: () -> Unit) {
    ListItem(headlineContent = { Text(label, fontWeight = FontWeight.SemiBold) },
        trailingContent = { Text(value, color = MaterialTheme.colorScheme.onSurfaceVariant) },
        modifier = Modifier.clickable(role = Role.Button, onClickLabel = label, onClick = onClick))
}

@Composable
private fun SettingsSection(label: String, divider: Boolean = true) {
    if (divider) HorizontalDivider(Modifier.padding(top = PresentationTokens.spaceMedium.dp), thickness = PresentationTokens.borderWidth.dp,
        color = MaterialTheme.colorScheme.outline)
    SidebarSectionHeading(label, start = PresentationTokens.spacePage.dp)
}

@Composable
private fun SettingsRow(label: String, onClick: () -> Unit, enabled: Boolean = true, danger: Boolean = false) {
    val color = if (danger) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface
    ListItem(headlineContent = { Text(label, color = color.copy(alpha = if (enabled) 1f else DisabledAlpha), fontWeight = FontWeight.SemiBold) },
        modifier = Modifier.clickable(enabled = enabled, role = Role.Button, onClick = onClick))
}

@Composable
private fun SettingsFooter(text: String) {
    Text(text, Modifier.padding(horizontal = PresentationTokens.spacePage.dp, vertical = PresentationTokens.spaceSmall.dp),
        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/** Question forms the user has replied to since, which are not offered again (desktop `isAnsweredQuestion`). */
private fun answeredQuestions(chat: Chat): Set<String> {
    val lastUser = chat.messages.indexOfLast { it.role == "user" }
    if (lastUser < 0) return emptySet()
    return chat.messages.take(lastUser).flatMap { it.parts }.mapNotNull { part ->
        part.surface?.takeIf { (it.component as? A2UIComponent.Form)?.action == "submit_question" }?.id
    }.toSet()
}

private fun surfaceHandler(model: MobileModel, chat: Chat): SurfaceHandler {
    val answered = answeredQuestions(chat)
    val idle = !model.busy && !model.streaming && !chat.running
    val canSend = model.device?.permissions?.send == true && chat.id.isNotEmpty()
    // A blocked question is answered while the run waits; anything else starts a new turn.
    return SurfaceHandler(
        interactive = { surface -> canSend && if (surface.deferred) model.surfacesSupported else idle && surface.id !in answered },
        act = { surface, action, context, done -> model.act(surface, action, context, done) })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ColumnScope.Conversation(model: MobileModel) {
    DisposableEffect(model) { onDispose { model.voice.stop() } }
    val chat = model.selected ?: return
    val railChoices = remember(chat.id) { RailChoices() }
    var streamGeneration by remember(chat.id) { mutableIntStateOf(0) }
    var sawStreaming by remember(chat.id) { mutableStateOf(false) }
    val streamStep = nextStreamGeneration(streamGeneration, sawStreaming, model.streaming)
    if (streamStep.first != streamGeneration || streamStep.second != sawStreaming) {
        streamGeneration = streamStep.first
        sawStreaming = streamStep.second
    }
    var attachmentsExpanded by remember(chat.id) { mutableStateOf(false) }
    val keyboardVisible = WindowInsets.ime.getBottom(LocalDensity.current) > 0
    val expanded = keyboardVisible && !attachmentsExpanded
    val loadingHistory = model.openingChatId == chat.id && chat.messages.isEmpty()
    val historyAlpha = animateFloatAsState(if (loadingHistory) 0f else 1f,
        animationSpec = tween(160, easing = FastOutSlowInEasing), label = "history reveal")
    LaunchedEffect(keyboardVisible) { if (keyboardVisible) attachmentsExpanded = false }
    androidx.activity.compose.BackHandler(enabled = attachmentsExpanded) { attachmentsExpanded = false }
    val keyboard = LocalSoftwareKeyboardController.current
    val focus = LocalFocusManager.current
    val context = androidx.compose.ui.platform.LocalContext.current
    // Keep the permission callback alive when hiding the keyboard moves the action button.
    val microphonePermission = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) model.startVoice() else model.error = context.getString(R.string.voice_permission) }
    val startVoice: () -> Unit = {
        val reason = model.voiceUnavailableReason
        if (reason != null) model.error = context.getString(reason)
        else {
            focus.clearFocus(); keyboard?.hide()
            microphonePermission.launch(android.Manifest.permission.RECORD_AUDIO)
        }
    }
    // Top-down like iOS, so a disclosure grows and shrinks below its header; a bottom-up (reversed) list held
    // each message's bottom edge instead and dragged the header along. Sticking to the end is done here.
    val scroll = remember(chat.id) { androidx.compose.foundation.lazy.LazyListState() }
    // Only the reader's own scrolling changes this, so content growing below never switches it off.
    var following by remember(chat.id) { mutableStateOf(true) }
    // Set during composition: effects run before the list lays out new items, so its layoutInfo is a pass behind.
    var lastItem by remember(chat.id) { mutableIntStateOf(-1) }
    suspend fun toEnd() {
        if (lastItem < 0) return
        // Lands the last item's top in view, then the list clamps the rest at its end. A huge delta overflows
        // the list's integer scroll arithmetic, so the remainder is bounded by one (tall) item.
        scroll.scrollToItem(lastItem)
        scroll.scrollBy(1_000_000f)
    }
    // Programmatic scrolls must not decide this: messages can arrive after the first scroll to the end.
    var dragged by remember(chat.id) { mutableStateOf(false) }
    LaunchedEffect(scroll) {
        scroll.interactionSource.interactions.collect { if (it is androidx.compose.foundation.interaction.DragInteraction.Start) { dragged = true; following = false } }
    }
    LaunchedEffect(scroll) {
        snapshotFlow { scroll.isScrollInProgress }.collect { moving -> if (!moving && dragged) { dragged = false; following = !scroll.canScrollForward } }
    }
    LaunchedEffect(scroll) { snapshotFlow { scroll.layoutInfo.viewportSize.height }.collect { if (following) toEnd() } }
    // Messages render their Markdown views after the first layout and grow, so keep following growth for a moment
    // after opening or sending, and while a reply streams; otherwise a disclosure the reader opens stays put.
    var settleUntil by remember(chat.id) { mutableLongStateOf(0L) }
    val streaming by rememberUpdatedState(model.streaming || model.liveParts.isNotEmpty())
    LaunchedEffect(scroll) {
        snapshotFlow { scroll.canScrollForward }.collect { more ->
            if (more && following && !dragged && (streaming || System.nanoTime() < settleUntil)) toEnd()
        }
    }
    LaunchedEffect(model.openedVersion) { following = true; settleUntil = System.nanoTime() + 1_500_000_000L; toEnd() }
    var modelsExpanded by remember(chat.id) { mutableStateOf(false) }
    LaunchedEffect(chat.id, model.openedVersion) { model.watchApprovals(chat.id) }
    LaunchedEffect(model.sentVersion) {
        if (model.sentVersion > 0) {
            attachmentsExpanded = false; keyboard?.hide(); focus.clearFocus()
            following = true; settleUntil = System.nanoTime() + 1_500_000_000L; toEnd()
        }
    }
    val trayHeight by androidx.compose.animation.core.animateDpAsState(
        targetValue = if (attachmentsExpanded) 200.dp else 0.dp,
        animationSpec = androidx.compose.animation.core.tween(220), label = "attachment tray")
    if (chat.isRegent) {
        val sessions = model.chats.filter { it.parentChatId == chat.id }.take(5)
        var sessionsExpanded by remember(chat.id) { mutableStateOf(false) }
        if (sessions.isNotEmpty()) Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
            SuzentTextButton(onClick = { sessionsExpanded = !sessionsExpanded }) {
                Text(stringResource(R.string.regent_sessions), fontSize = PresentationTokens.typeLabel.sp)
                SuzentChevron(sessionsExpanded, Modifier.padding(start = 6.dp), size = 14.dp)
            }
            if (sessionsExpanded) sessions.forEach { session ->
                SuzentTextButton(onClick = { model.open(session) }, enabled = !model.busy) {
                    Text(session.title, fontSize = 13.sp, maxLines = 1, modifier = Modifier.weight(1f))
                    SuzentChevron(false, size = 14.dp)
                }
            }
        }
    }
    val mediaLoader: suspend (MediaItem) -> java.io.File? = remember(chat.id) { { item -> model.mediaFile(chat.id, item) } }
    CompositionLocalProvider(LocalRailChoices provides railChoices, LocalMediaLoader provides mediaLoader) {
    BoxWithConstraints(Modifier.weight(1f).fillMaxWidth().clipToBounds()) {
    val viewportHeight = maxHeight
    Column(Modifier.fillMaxWidth().requiredHeight(viewportHeight).offset(y = -trayHeight)) {
    val liveTools = model.liveParts.filter { it.type == "tool" }.map { it.toolCallId }.toSet()
    val savedMessages = remember(chat.messages, liveTools) { presentMessages(chat.messages, liveTools) }
    val messages = remember(savedMessages, chat.isRegent, model.liveParts) { if (chat.isRegent) regentMessages(savedMessages, model.liveParts) else savedMessages }
    val live = model.streaming || model.liveParts.isNotEmpty()
    lastItem = (if (chat.id.isEmpty()) 1 else 0) + (if (chat.isRegent && messages.isEmpty() && !model.streaming) 1 else 0) +
        messages.size + (if (live) 1 else 0) - 1
    var positionedVersion by remember(chat.id) { mutableIntStateOf(-1) }
    if (!loadingHistory && positionedVersion != model.openedVersion && lastItem >= 0) {
        SideEffect {
            scroll.requestScrollToItem(lastItem)
            positionedVersion = model.openedVersion
        }
    }
    // Follow a streaming reply, and the hand-off from the live turn to the saved message, while at the end.
    LaunchedEffect(model.liveParts, messages.size) { if (following && chat.id.isNotEmpty()) toEnd() }
    LazyColumn(Modifier.weight(1f).fillMaxWidth().graphicsLayer {
        alpha = if (loadingHistory) 1f else historyAlpha.value
    }.pointerInput(attachmentsExpanded) {
        if (attachmentsExpanded) awaitEachGesture {
            // Observe before selectable text and message controls consume the touch.
            awaitFirstDown(requireUnconsumed = false, pass = androidx.compose.ui.input.pointer.PointerEventPass.Initial)
            attachmentsExpanded = false
        }
    }.pointerInput(Unit) {
        detectTapGestures(onTap = { attachmentsExpanded = false; keyboard?.hide(); focus.clearFocus() })
    }, state = scroll, contentPadding = PaddingValues(16.dp),
        // Short conversations sit at the bottom, as they did when the list was reversed.
        verticalArrangement = Arrangement.spacedBy(PresentationTokens.spaceLarge.dp, if (chat.id.isEmpty()) Alignment.Top else Alignment.Bottom)) {
        if (chat.id.isEmpty()) item { StartPage(model, chat, expanded) }
        if (loadingHistory) item(key = "loading-history") {
            HistoryLoadingIndicator()
        }
        if (!loadingHistory && chat.isRegent && messages.isEmpty() && !model.streaming) item { RegentGreeting() }
        itemsIndexed(messages, key = { index, _ -> "message-$index" }) { index, message ->
            val idle = !model.busy && !model.streaming && !chat.running
            val lastUser = chat.messages.indexOfLast { it.role == "user" }
            val newest = index == messages.lastIndex
            val canReplay = !chat.isRegent && idle && chat.models.isNotEmpty() && lastUser >= 0 && model.device?.permissions?.send == true && model.device?.permissions?.manageChats == true
            CompositionLocalProvider(LocalRailScope provides railScope(chat.id, "m${message.messageIndex}")) {
            MessageView(message, regent = chat.isRegent, isLatest = newest && !model.streaming && model.liveParts.isEmpty(), fallbackModel = chat.model,
                canRetry = canReplay && (message.messageIndex == lastUser || (newest && message.role == "assistant")),
                canEdit = canReplay && message.role == "user" && message.messageIndex == lastUser,
                canFork = !chat.isRegent && idle && message.role == "assistant" && model.device?.permissions?.createChats == true,
                onAction = { action, text -> model.messageAction(message, action, text) })
            }
        }
        if (live) item(key = "live") {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                CompositionLocalProvider(LocalRailScope provides railScope(chat.id, "live$streamGeneration")) {
                ActivityTurn(if (chat.isRegent) regentDisplayParts(model.liveParts, model.streaming) else model.liveParts,
                    live = model.streaming, regent = chat.isRegent)
                }
            }
        }
    }
    if (model.pendingApprovals.isNotEmpty()) Box(Modifier.fillMaxWidth().heightIn(max = viewportHeight * .4f)
        .verticalScroll(rememberScrollState()).padding(horizontal = 12.dp).padding(top = 8.dp)) { ApprovalCards(model) }
    SuzentErrorHost(model)
    val composerOutline = MaterialTheme.colorScheme.outline
    val composerShadow = suzentShadow
    Box(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp).drawBehind {
        val offset = PresentationTokens.shadowOffset.dp.toPx()
        drawRect(composerShadow, topLeft = androidx.compose.ui.geometry.Offset(offset, offset), size = Size(size.width - offset, size.height - offset))
    }.padding(end = PresentationTokens.shadowOffset.dp, bottom = PresentationTokens.shadowOffset.dp)) {
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
        .border(PresentationTokens.borderWidth.dp, composerOutline)
        .animateContentSize(
            animationSpec = spring(dampingRatio = Spring.DampingRatioNoBouncy, stiffness = Spring.StiffnessMediumLow),
            alignment = Alignment.BottomCenter
        ).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        QueuedMessages(model)
        if (model.voice.active) {
            VoiceCubeView(model.voice.animationState, model.voice.working, model.voice.micLevel, Modifier.fillMaxWidth().height(112.dp))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(stringResource(model.voice.status), fontSize = 14.sp)
                if (model.voice.transcript.isNotEmpty()) Text(model.voice.transcript, fontSize = 14.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
            }

            }
        }
        PendingAttachmentStrip(model)
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        if (!chat.isRegent && model.attachmentsSupported && model.device?.permissions?.send == true)
            SuzentIconButton(onClick = {
                attachmentsExpanded = !attachmentsExpanded
                if (attachmentsExpanded) { focus.clearFocus(); keyboard?.hide() }
            }, label = stringResource(R.string.attach), enabled = !model.busy && model.attachments.size < MAX_ATTACHMENTS) {
                Icon(painterResource(R.drawable.ic_attach), null)
            }
        BasicTextField(value = model.draft, onValueChange = { model.draft = it }, enabled = !model.busy,
            modifier = Modifier.weight(1f).heightIn(min = 44.dp).padding(horizontal = 4.dp, vertical = 12.dp), minLines = 1, maxLines = if (expanded) 6 else 1,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Default),
            textStyle = MaterialTheme.typography.bodyMedium.copy(fontSize = PresentationTokens.typeChat.sp, color = MaterialTheme.colorScheme.onSurface),
            cursorBrush = androidx.compose.ui.graphics.SolidColor(suzentLink),
            decorationBox = { inner -> Box { if (model.draft.isEmpty()) Text(stringResource(R.string.message), fontSize = PresentationTokens.typeChat.sp, color = MaterialTheme.colorScheme.onSurfaceVariant); inner() } })
        Spacer(Modifier.width(if (composerAction(model, chat) == ComposerAction.REDIRECT) 88.dp else 44.dp))
        }
        AnimatedVisibility(visible = expanded,
            enter = fadeIn(tween(160, delayMillis = 40)),
            exit = fadeOut(tween(90))) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) {
                SuzentTextButton(onClick = { modelsExpanded = true; focus.clearFocus(); keyboard?.hide() },
                    enabled = !model.busy && !model.streaming && chat.models.isNotEmpty() && model.device?.permissions?.send == true) {
                    Text(model.selectedModel ?: chat.model ?: stringResource(R.string.desktop_model),
                        modifier = Modifier.weight(1f, fill = false), maxLines = 1, overflow = TextOverflow.MiddleEllipsis,
                        fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Icon(painterResource(R.drawable.ic_chevron_down), contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = 4.dp).size(14.dp))
                }

            }
            Spacer(Modifier.size(if (composerAction(model, chat) == ComposerAction.REDIRECT) 88.dp else 44.dp))
        }
        }
    }
    // One persistent action stays at the animated panel's bottom edge in both layouts.
    Box(Modifier.align(Alignment.BottomEnd).padding(10.dp)) {
        SendAction(model, chat, startVoice)
    }
    }
    }
    Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(trayHeight).clipToBounds()) {
        Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().requiredHeight(200.dp)) {
            if (!chat.isRegent) AttachmentPanel(model, close = { attachmentsExpanded = false })
        }
    }
    }
    if (modelsExpanded) SuzentSelectionPanel(
        title = stringResource(R.string.desktop_model),
        options = listOf("" to stringResource(R.string.conversation_default)) + chat.models.distinct().sorted().map { it to it },
        selected = model.selectedModel.orEmpty(), dismiss = { modelsExpanded = false }
    ) { model.selectModel(it.ifEmpty { null }); modelsExpanded = false }

}
}

@Composable
private fun HistoryLoadingIndicator() {
    var visible by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(180)
        visible = true
    }
    Box(Modifier.fillMaxWidth().height(68.dp), contentAlignment = Alignment.Center) {
        AnimatedVisibility(visible, enter = fadeIn(tween(140)), exit = fadeOut(tween(90))) {
            CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun composerAction(model: MobileModel, chat: Chat) = ComposerAction.resolve(model.draft.isNotBlank() || model.attachments.isNotEmpty(),
    model.busy, model.streaming || chat.running, model.voice.active, model.voice.animationState == "connecting",
    canRedirect = model.draft.isNotBlank() && model.redirectSupported)

@Composable
private fun SendAction(model: MobileModel, chat: Chat, startVoice: () -> Unit) {
    val action = composerAction(model, chat)
    val queued = model.queued
    LaunchedEffect(chat.id, queued, model.busy, model.streaming, chat.running, model.pendingApprovals.isEmpty(), model.approvalBusy) {
        model.releaseQueued()
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        // Redirect is the main action mid-turn, as Enter is on desktop; waiting for the turn to end sits beside it.
        if (action == ComposerAction.REDIRECT) ComposerButton(ComposerAction.QUEUE, model, chat, startVoice)
        ComposerButton(action, model, chat, startVoice)
    }
}

@Composable
private fun ComposerButton(action: ComposerAction, model: MobileModel, chat: Chat, startVoice: () -> Unit) {
    val view = LocalView.current
    val context = androidx.compose.ui.platform.LocalContext.current
    val loading = action == ComposerAction.LOADING || (action == ComposerAction.STOP && model.stopInFlight)
    val label = stringResource(when (action) {
        ComposerAction.VOICE -> R.string.voice_start
        ComposerAction.SEND -> R.string.send
        ComposerAction.CONNECTING -> R.string.voice_cancel_connection
        ComposerAction.HANG_UP -> R.string.voice_end
        ComposerAction.STOP -> if (model.stopInFlight) R.string.composer_stopping else R.string.stop
        ComposerAction.LOADING -> R.string.composer_processing
        ComposerAction.QUEUE -> R.string.composer_queue
        ComposerAction.REDIRECT -> R.string.composer_redirect
    })
    Box(Modifier.size(44.dp).clickable(enabled = !loading, role = Role.Button, onClickLabel = label) {
        when (action) {
            ComposerAction.STOP -> if (model.device?.permissions?.stop == true) model.stop()
                else model.error = context.getString(R.string.composer_grant_required)
            ComposerAction.HANG_UP, ComposerAction.CONNECTING -> model.voice.stop()
            ComposerAction.VOICE -> startVoice()
            ComposerAction.SEND -> when {
                model.device?.permissions?.send != true -> model.error = context.getString(R.string.composer_grant_required)
                chat.id.isEmpty() && model.device?.permissions?.createChats != true -> model.error = context.getString(R.string.composer_create_required)
                else -> { view.suzentHaptic(SuzentHaptic.Light); model.send() }
            }
            ComposerAction.QUEUE, ComposerAction.REDIRECT -> when {
                model.device?.permissions?.send != true -> model.error = context.getString(R.string.composer_grant_required)
                else -> { view.suzentHaptic(SuzentHaptic.Light); if (action == ComposerAction.QUEUE) model.queue() else model.redirect() }
            }
            ComposerAction.LOADING -> Unit
        }
    }.semantics { contentDescription = label }, contentAlignment = Alignment.Center) {
        val fill = when (action) {
            ComposerAction.STOP, ComposerAction.HANG_UP -> Color(PresentationTokens.danger)
            ComposerAction.REDIRECT -> Color(PresentationTokens.yellow)
            ComposerAction.QUEUE -> MaterialTheme.colorScheme.surface
            else -> MaterialTheme.colorScheme.primary
        }
        val tint = when (action) {
            ComposerAction.REDIRECT -> Color.Black
            ComposerAction.QUEUE -> MaterialTheme.colorScheme.onSurface
            else -> Color.White
        }
        Box(Modifier.size(36.dp).background(fill)
            .border(2.dp, MaterialTheme.colorScheme.outline), contentAlignment = Alignment.Center) {
            if (loading || action == ComposerAction.CONNECTING) CircularProgressIndicator(Modifier.size(18.dp), color = tint, strokeWidth = 2.dp)
            else Icon(painterResource(when (action) {
                ComposerAction.STOP -> R.drawable.ic_stop
                ComposerAction.HANG_UP -> R.drawable.ic_hang_up
                ComposerAction.VOICE -> R.drawable.ic_voice
                ComposerAction.QUEUE -> R.drawable.ic_clock
                ComposerAction.REDIRECT -> R.drawable.ic_redirect
                else -> R.drawable.ic_send
            }), contentDescription = null, tint = tint, modifier = Modifier.size(20.dp))
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
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(28.dp)) {
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
private fun SidebarSectionHeading(label: String, count: Int? = null, start: Dp = 12.dp) {
    // Desktop section headings: 10px extrabold uppercase, 0.16em tracking, muted.
    Row(Modifier.fillMaxWidth().padding(start = start, top = 12.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(label.uppercase(java.util.Locale.getDefault()), fontWeight = FontWeight.ExtraBold,
            fontSize = PresentationTokens.typeSidebarSection.sp, letterSpacing = 1.6.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
        if (count != null) Text(count.toString(), fontWeight = FontWeight.Bold,
            fontSize = PresentationTokens.typeSidebarSection.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private enum class HomeListMode(val label: Int) { RECENT(R.string.recent_chats), PROJECTS(R.string.sidebar_projects) }

@Composable
private fun HomeListPicker(selection: HomeListMode, select: (HomeListMode) -> Unit, modifier: Modifier = Modifier) {
    SuzentSegmentedTabs(HomeListMode.entries, selection, select, { stringResource(it.label) }, modifier)
}

private enum class HomeTab(val label: Int, val icon: Int) {
    CHATS(R.string.tab_chats, R.drawable.ic_tool_chat_bubble_left_right),
    INBOX(R.string.mailbox_title, R.drawable.ic_inbox),
    SETTINGS(R.string.settings, R.drawable.ic_settings)
}

/** Phone home: one page per tab above a bottom bar. A pushed conversation covers the bar entirely. */
@Composable
private fun TabHome(tab: HomeTab, select: (HomeTab) -> Unit, unread: Int = 0, page: @Composable (HomeTab) -> Unit) {
    // The keyboard covers the bar anyway; dropping it keeps the page's own ime padding exact.
    val keyboardVisible = WindowInsets.ime.getBottom(LocalDensity.current) > 0
    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f).fillMaxWidth()) { page(tab) }
        if (!keyboardVisible) {
            HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
            Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).navigationBarsPadding().selectableGroup()) {
                HomeTab.entries.forEach { item ->
                    val selected = item == tab
                    val color = if (selected) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
                    Column(Modifier.weight(1f).heightIn(min = 56.dp).selectable(selected, role = Role.Tab) { select(item) }
                        .drawBehind { if (selected) drawRect(color, androidx.compose.ui.geometry.Offset((size.width - 32.dp.toPx()) / 2, 0f), Size(32.dp.toPx(), 3.dp.toPx())) }
                        .padding(vertical = 6.dp),
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                        BadgedBox(badge = { if (item == HomeTab.INBOX && unread > 0) Badge { Text(if (unread > 99) "99+" else unread.toString()) } }) {
                            Icon(painterResource(item.icon), contentDescription = null, tint = color, modifier = Modifier.size(22.dp))
                        }
                        Text(stringResource(item.label), fontSize = PresentationTokens.typeMeta.sp, color = color,
                            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal, maxLines = 1)
                    }
                }
            }
        }
    }
}

@Composable
internal fun TabTitle(title: String, model: MobileModel? = null) {
    Column(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center) {
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, maxLines = 1)
        model?.let { ActiveDesktopLabel(it) }
    }
    HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
}

@Composable
private fun ActiveDesktopLabel(model: MobileModel, modifier: Modifier = Modifier) {
    val desktop = model.desktops.active ?: return
    if (model.isDemo) return
    Row(modifier.semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Icon(painterResource(R.drawable.ic_desktop), contentDescription = null, modifier = Modifier.size(14.dp),
            tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(desktop.name, fontSize = PresentationTokens.typeLabel.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun DesktopSquare(id: String, size: Dp) {
    Box(Modifier.size(size).background(Color(desktopColor(id))).border(1.5.dp, MaterialTheme.colorScheme.onSurface))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun InboxTasks(model: MobileModel, open: (Chat) -> Unit) {
    var expandedAgents by remember { mutableStateOf(setOf<String>()) }
    fun toggleAgents(id: String) { expandedAgents = if (id in expandedAgents) expandedAgents - id else expandedAgents + id }
    val groups = scheduledSidebarGroups(model.chats, model.scheduledTasks, "", expandedAgents)
    val scope = rememberCoroutineScope()
    var refreshing by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize()) {
        PullToRefreshBox(isRefreshing = refreshing, modifier = Modifier.weight(1f).fillMaxWidth(), onRefresh = {
            refreshing = true
            scope.launch { try { model.refresh().join() } finally { refreshing = false } }
        }) {
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
                if (groups.isEmpty()) item(key = "empty") {
                    Text(stringResource(R.string.tasks_empty), Modifier.padding(vertical = 24.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                items(groups, key = { it.id }) { group ->
                    Column {
                        val task = group.task
                        val root = group.root
                        if (task != null) ScheduledTaskRow(task, model, false, root?.childCount ?: 0, task.chatId in expandedAgents,
                            { task.chatId?.let(::toggleAgents) }) {
                            task.chatId?.let { id -> open(model.chats.firstOrNull { it.id == id } ?: Chat(id, task.name, task.running, emptyList())) }
                        }
                        else if (root != null) SidebarEntry(root, false, model, open, root.chat.id in expandedAgents) { toggleAgents(root.chat.id) }
                        group.children.forEach { entry -> SidebarEntry(entry, false, model, open, false) {} }
                    }
                }
            }
        }
    }
}

@Composable
private fun DesktopsView(model: MobileModel, back: () -> Unit) {
    var scanner by remember { mutableStateOf(false) }
    if (scanner) PairingScanner(model) { scanner = false }
    var forgetting by remember { mutableStateOf<SavedDesktop?>(null) }
    forgetting?.let { desktop ->
        AlertDialog(onDismissRequest = { forgetting = null }, title = { Text(stringResource(R.string.forget_desktop_title, desktop.name)) },
            text = { Text(stringResource(R.string.forget_warning)) },
            confirmButton = { TextButton(onClick = { forgetting = null; model.forgetDesktop(desktop.id) }, enabled = !model.busy) {
                Text(stringResource(R.string.forget_desktop), color = MaterialTheme.colorScheme.error)
            } },
            dismissButton = { TextButton(onClick = { forgetting = null }) { Text(stringResource(android.R.string.cancel)) } })
    }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            SuzentIconButton(onClick = back, label = stringResource(R.string.back)) {
                Icon(painterResource(R.drawable.ic_chat_back), contentDescription = null, modifier = Modifier.size(20.dp))
            }
            Text(stringResource(R.string.desktops), Modifier.weight(1f), style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            Spacer(Modifier.size(PresentationTokens.controlHeight.dp))
        }
        HorizontalDivider(thickness = PresentationTokens.borderWidth.dp, color = MaterialTheme.colorScheme.outline)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            SettingsSection(stringResource(R.string.paired_desktops), divider = false)
            model.desktops.desktops.forEach { desktop ->
                key(desktop.id) { DesktopRow(model, desktop) { forgetting = desktop } }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            }
            OutlinedButton(onClick = { model.error = null; model.beginPairing(repairActive = false); scanner = true },
                enabled = !model.busy && !model.streaming, shape = RectangleShape,
                border = androidx.compose.foundation.BorderStroke(PresentationTokens.borderWidth.dp, MaterialTheme.colorScheme.outline),
                modifier = Modifier.padding(PresentationTokens.spacePage.dp).fillMaxWidth().heightIn(min = 48.dp)) {
                Text(stringResource(R.string.pair_another_desktop), fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurface)
            }
            SettingsFooter(stringResource(R.string.desktops_footer))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DesktopRow(model: MobileModel, desktop: SavedDesktop, forget: () -> Unit) {
    val active = desktop.id == model.desktops.activeId
    val checking = model.checkingDesktop == desktop.id
    val forgetLabel = stringResource(R.string.forget_desktop)
    val latestForget by rememberUpdatedState(forget)
    // The swipe only asks; the dialog does the forgetting, so the row always springs back.
    val swipe = rememberSwipeToDismissBoxState(confirmValueChange = {
        if (it == SwipeToDismissBoxValue.EndToStart) latestForget()
        false
    })
    SwipeToDismissBox(swipe, enableDismissFromStartToEnd = false, backgroundContent = {
        Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.error).padding(horizontal = PresentationTokens.spacePage.dp),
            contentAlignment = Alignment.CenterEnd) {
            Text(forgetLabel, color = MaterialTheme.colorScheme.onError, fontWeight = FontWeight.SemiBold)
        }
    }) {
        ListItem(leadingContent = { DesktopSquare(desktop.id, 14.dp) },
            headlineContent = { Text(desktop.name, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis) },
            supportingContent = { Text(if (checking) stringResource(R.string.desktop_checking) else displayOrigin(desktop.connection.origin),
                maxLines = 1, overflow = TextOverflow.Ellipsis) },
            trailingContent = {
                when {
                    checking -> CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    active -> Icon(painterResource(R.drawable.ic_message_check), contentDescription = stringResource(R.string.desktop_current),
                        tint = suzentLink, modifier = Modifier.size(20.dp))
                }
            },
            modifier = Modifier
                .semantics { customActions = listOf(CustomAccessibilityAction(forgetLabel) { latestForget(); true }) }
                .clickable(enabled = !active && model.checkingDesktop == null && !model.streaming, role = Role.Button) { model.switchDesktop(desktop.id) })
    }
}
