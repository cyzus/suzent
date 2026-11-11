package com.suzent.mobile

import android.app.Application
import android.net.Uri
import android.provider.Settings
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.TimeoutCancellationException
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

class MobileModel(application: Application) : AndroidViewModel(application) {
    var origin by mutableStateOf("")
    var invitationText by mutableStateOf("")
    var pairingInvitation by mutableStateOf<PairingInvitation?>(null)
    var pairingPreview by mutableStateOf<PairingPreview?>(null)
    var pairingStatus by mutableStateOf<String?>(null)
    var awaitingDesktop by mutableStateOf(false)
    var device by mutableStateOf<ClientDevice?>(null)
    var canReconnect by mutableStateOf(false)
    var reconnecting by mutableStateOf(false)
    var reconnectStage by mutableStateOf(0)
        private set
    var reconnectStatus by mutableStateOf<String?>(null)
        private set
    private var reconnectJob: Job? = null
    private var pairingJob: Job? = null
    var scheduledTasks by mutableStateOf<List<ScheduledTask>>(emptyList())
        private set
    var projects by mutableStateOf<List<Project>>(emptyList())
    var selectedModel by mutableStateOf<String?>(null)
    private val modelPreferences = application.getSharedPreferences("model_preferences", android.content.Context.MODE_PRIVATE)

    var sentVersion by mutableStateOf(0)
    var openedVersion by mutableStateOf(0)
    var openingChatId by mutableStateOf<String?>(null)
        private set
    var pinnedVersion by mutableStateOf(0)
    var pairingVersion by mutableStateOf(0)
    private val drafts = mutableMapOf<String, String>()
    var chatPages by mutableStateOf<Map<ChatPageQuery, ChatPage>>(emptyMap())
        private set
    var loadingPages by mutableStateOf<Set<ChatPageQuery>>(emptySet())
        private set
    private var navigationRevision = 0
    var navigationVersion by mutableStateOf(0)
        private set
    private var lastNavigationRefresh = 0L

    fun pageChats(query: ChatPageQuery): List<Chat> {
        val byId = chats.associateBy { it.id }
        return chatPages[query]?.chats.orEmpty().mapNotNull { byId[it.id] }
    }
    suspend fun loadPage(query: ChatPageQuery, more: Boolean = false) {
        val api = client ?: return
        if (query in loadingPages || !more && query in chatPages) return
        val offset = if (more) chatPages[query]?.nextOffset ?: return else 0
        val current = generation
        val revision = navigationRevision
        loadingPages = loadingPages + query
        try {
            val page = api.chatPage(query, offset, 30)
            currentCoroutineContext().ensureActive()
            if (current != generation || revision != navigationRevision) return
            if (query.kind == "search") chatPages = chatPages.filterKeys { it.kind != "search" || it == query }
            chatPages = chatPages + (query to if (more) chatPages[query]?.appending(page) ?: page else page)
            mergeNavigationChats(page.chats)
            val retained = chatPages.values.flatMap { it.chats.map { chat -> chat.id } }.toSet()
            chats = chats.filter { it.isRegent || it.id == selected?.id || it.id in retained }
        } catch (failure: CancellationException) { throw failure }
        catch (failure: Exception) { if (current == generation && revision == navigationRevision) handle(failure) }
        finally { if (revision == navigationRevision) loadingPages = loadingPages - query }
    }
    private fun mergeNavigationChats(updates: List<Chat>) {
        val ids = updates.map { it.id }.toSet()
        chats = chats.filterNot { it.id in ids } + updates
    }
    private fun applyNavigation(initial: InitialNavigation) {
        navigationRevision++
        navigationVersion++
        loadingPages = emptySet()
        chatPages = mapOf(ChatPageQuery() to initial.recent, ChatPageQuery("pinned") to initial.pinned)
        chats = initial.chats
        projects = initial.metadata.projects
        lastNavigationRefresh = System.currentTimeMillis()
    }
    private suspend fun refreshNavigation(api: MobileClient, poll: Boolean) {
        val current = generation
        val revision = navigationRevision
        if (!poll || chatPages.isEmpty()) {
            val initial = api.initialNavigation()
            if (current != generation || revision != navigationRevision) return
            applyNavigation(initial)
        } else {
            val requested = chats.map { it.id }.toSet()
            val updates = api.chatStatuses(requested.toList())
            if (current != generation || revision != navigationRevision) return
            chats = chats.filterNot { it.id in requested } + updates
            // Collapsed projects have no loaded rows, so their running and unread marks come from metadata.
            val metadata = api.navigationMetadata()
            if (current != generation || revision != navigationRevision) return
            projects = metadata.projects
            metadata.regent?.let { mergeNavigationChats(listOf(it)) }
            if (System.currentTimeMillis() - lastNavigationRefresh >= 60_000) {
                val recentIds = chatPages[ChatPageQuery()]?.chats?.map { it.id }
                val pinnedIds = chatPages[ChatPageQuery("pinned")]?.chats?.map { it.id }
                val recent = if ((chatPages[ChatPageQuery()]?.chats?.size ?: 0) <= 30) api.chatPage(ChatPageQuery()) else null
                val pinned = if ((chatPages[ChatPageQuery("pinned")]?.chats?.size ?: 0) <= 30) api.chatPage(ChatPageQuery("pinned")) else null
                if (current != generation || revision != navigationRevision) return
                if (recent != null && ChatPageQuery() !in loadingPages && chatPages[ChatPageQuery()]?.chats?.map { it.id } == recentIds) {
                    chatPages = chatPages + (ChatPageQuery() to recent); mergeNavigationChats(recent.chats)
                }
                if (pinned != null && ChatPageQuery("pinned") !in loadingPages && chatPages[ChatPageQuery("pinned")]?.chats?.map { it.id } == pinnedIds) {
                    chatPages = chatPages + (ChatPageQuery("pinned") to pinned); mergeNavigationChats(pinned.chats)
                }
                lastNavigationRefresh = System.currentTimeMillis()
            }
        }
    }

    var chats by mutableStateOf<List<Chat>>(emptyList())
    var selected by mutableStateOf<Chat?>(null)
    var draft by mutableStateOf("")
    var attachments by mutableStateOf<List<PendingAttachment>>(emptyList())
    var attachmentsSupported by mutableStateOf(false)
    var regentVisible = false
    /** The open conversation is on screen, so its finished replies count as read. */
    var chatVisible by mutableStateOf(false)
    var liveParts by mutableStateOf<List<MessagePart>>(emptyList())
    var pendingApprovals by mutableStateOf<List<ApprovalRequest>>(emptyList())
    var approvalChoices by mutableStateOf<Map<String, String>>(emptyMap())
    var approvalBusy by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var busy by mutableStateOf(false)
    /** Loading the demo keeps the welcome screen up instead of the pairing progress view. */
    var startingDemo by mutableStateOf(false)
        private set
    var streaming by mutableStateOf(false)
    var isDemo by mutableStateOf(false)
        private set
    var demoPrompts by mutableStateOf<List<String>>(emptyList())
        private set
    var connected by mutableStateOf(false)
    var nodeEnabled by mutableStateOf(false)
    var nodeStatus by mutableStateOf(text(R.string.node_off))
    private val store = CredentialStore(application)
    var desktops by mutableStateOf(SavedDesktops())
        private set
    /** The saved desktop being probed before a switch; the current one stays usable meanwhile. */
    var checkingDesktop by mutableStateOf<String?>(null)
        private set
    private var switchJob: Job? = null
    private var repairActive = false
    private val connection: Connection? get() = desktops.active?.connection
    private var client: MobileClient? = null
    private val connectionUpgrade = ConnectionUpgrade<BackendClient>(viewModelScope)
    // Previously captured clients may still serve polling requests or the device socket.
    private val retiredClients = mutableListOf<MobileClient>()
    val voice = VoiceSession(application, viewModelScope, { error = text(it) }, { refresh() })
    val voiceSupported: Boolean get() = (client as? BackendClient)?.supportsVoice == true
    val overviewSupported: Boolean get() = client?.supportsChatOverview == true

    /** The plan and context panel reads on demand; null while unavailable. */
    suspend fun overview(chatId: String): ChatOverview? {
        val api = client?.takeIf { it.supportsChatOverview && chatId.isNotEmpty() } ?: return null
        return try { api.overview(chatId) } catch (failure: CancellationException) { throw failure } catch (_: Exception) { null }
    }

    val voiceUnavailableReason: Int? get() = when {
        isDemo -> R.string.voice_demo_unavailable
        !voiceSupported -> R.string.voice_setup_required
        device?.permissions?.send != true || device?.permissions?.stop != true -> R.string.voice_grant_required
        selected?.id?.isEmpty() == true && device?.permissions?.createChats != true -> R.string.composer_create_required
        else -> null
    }

    fun startVoice() {
        voiceUnavailableReason?.let { error = text(it); return }
        val api = client as? BackendClient ?: return
        val chat = selected ?: return
        if (!voiceSupported || busy || streaming || device?.permissions?.send != true || device?.permissions?.stop != true) return
        error = null
        val current = generation
        voice.start {
            var id = chat.id
            if (id.isEmpty()) {
                check(device?.permissions?.createChats == true)
                busy = true
                val created = try { api.create(text(R.string.voice_conversation), chat.projectId) } finally { busy = false }
                currentCoroutineContext().ensureActive()
                check(current == generation)
                selected = created
                chats = listOf(created) + chats
                id = created.id
            }
            api to id
        }
    }

    private var streamJob: Job? = null
    private var socket: WebSocket? = null
    private var foreground = false
    private var generation = 0

    private fun text(id: Int, vararg args: Any): String = getApplication<Application>().getString(id, *args)

    private fun relayClient(route: RelayRoute, token: String, probeOnly: Boolean = false) =
        BackendClient(Backend(RelayRoute.placeholder), token, probeOnly, relay = route)

    init {
        AttachmentFiles.clear(application)
        try {
            desktops = store.load()
            origin = connection?.origin.orEmpty()
            canReconnect = connection?.clientProtocol == 1
        } catch (_: Exception) { error = text(R.string.secure_error) }
    }

    fun startDemo() {
        if (busy || streaming) return
        busy = true
        startingDemo = true
        viewModelScope.launch {
            try {
                val app = getApplication<Application>()
                val demo = withContext(Dispatchers.IO) {
                    DemoClient(app.assets.open("demo.json").bufferedReader().use { it.readText() },
                        java.io.File(app.filesDir, "offline-demo/workspace.json"))
                }
                val session = demo.session()
                val navigation = demo.initialNavigation()
                val taskList = demo.scheduledTasks()
                val composer = demo.composer()
                clearSession()
                error = null
                client = demo
                isDemo = true
                demoPrompts = demo.prompts
                origin = "demo://offline"
                canReconnect = false
                device = session
                attachmentsSupported = true
                applyNavigation(navigation); scheduledTasks = taskList
                selected = composer
                connected = true
                openedVersion++
            } catch (failure: CancellationException) { throw failure }
            catch (_: Exception) { error = text(R.string.demo_load_error) }
            finally { busy = false; startingDemo = false }
        }
    }

    fun resetDemo() {
        val demo = client as? DemoClient ?: return
        if (busy) return
        generation++
        streamJob?.cancel(); streaming = false; liveParts = emptyList()
        pendingApprovals = emptyList(); approvalChoices = emptyMap(); approvalBusy = false; drafts.clear(); draft = ""; error = null
        discardAttachments()
        viewModelScope.launch {
            try {
                demo.reset()
                selected = demo.composer()
                selectedModel = null
                refreshNow()
                openedVersion++
            } catch (failure: CancellationException) { throw failure }
            catch (_: Exception) { error = text(R.string.demo_load_error) }
        }
    }

    fun exitDemo() {
        if (!isDemo || busy) return
        clearSession()
        isDemo = false; demoPrompts = emptyList(); error = null
    }

    /** Repairing re-pairs the active desktop; otherwise a scanned desktop that is already saved is recognised by its identity. */
    fun beginPairing(repairActive: Boolean) { this.repairActive = repairActive }

    fun stageInvitation(value: String) {
        if (busy) return
        val invitation = try { PairingInvitation.parse(value, BuildConfig.DEBUG) }
        catch (failure: Exception) { handle(failure); return }
        invitationText = ""
        pairingInvitation = null
        pairingPreview = null
        error = null
        busy = true
        val current = generation
        pairingStatus = text(R.string.pairing_recognized_connecting)
        pairingJob = viewModelScope.launch {
            try {
                val selected = try {
                    resolvePairingInvitation(invitation) { origin ->
                        val trust = invitation.tls ?: invitation.tlsFingerprint?.let { DeviceTrust.fetch(origin, it) }
                        val probe = BackendClient(Backend.parse(origin, BuildConfig.DEBUG), "", probeOnly = true, deviceTrust = trust)
                        try {
                            probe.capabilities()
                            trust to if (invitation.phoneConfirmation) probe.pairingPreview(invitation) else null
                        } finally { probe.close() }
                    }
                } catch (failure: PairingFailure) {
                    // No direct address answered: try the desktop's relay, if it offered one.
                    val relay = invitation.relay
                    if (relay == null || failure.reason == PairingFailure.Reason.EXPIRED) throw failure
                    val probe = relayClient(relay, "", probeOnly = true)
                    try {
                        probe.capabilities()
                        invitation.copy(viaRelay = true) to (invitation.tls to if (invitation.phoneConfirmation) probe.pairingPreview(invitation) else null)
                    } catch (error: CancellationException) { throw error }
                    catch (_: Exception) { throw failure }
                    finally { probe.close() }
                }
                if (current == generation) { pairingPreview = selected.second.second; pairingInvitation = selected.first.copy(tls = selected.second.first) }
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { if (current == generation) handle(failure) }
            finally { if (current == generation) { busy = false; pairingStatus = null } }
        }
    }

    fun cancelPairing() {
        pairingJob?.cancel()
        pairingJob = null
        pairingStatus = null
        pairingInvitation = null
        awaitingDesktop = false
        pairingPreview = null
        generation++
        busy = false
    }

    fun approveDestination() {
        val invitation = pairingInvitation ?: return
        if (busy) return
        busy = true
        error = null
        val current = generation
        pairingStatus = text(R.string.pairing_sending)
        pairingJob = viewModelScope.launch {
            val bootstrap = invitation.relay?.takeIf { invitation.viaRelay }?.let { relayClient(it, "") }
                ?: BackendClient(Backend.parse(invitation.origin, BuildConfig.DEBUG), "", deviceTrust = invitation.tls)
            val bootstrapOrigin = if (invitation.viaRelay) invitation.origin else bootstrap.backend.origin.toString()
            val target = if (repairActive) desktops.active else desktops.matching(invitation)
            val known = target?.connection
            val desktopName = pairingPreview?.desktopName
            try {
                bootstrap.capabilities()
                val previous = known?.hostToken?.takeIf { bootstrap.supportsPairingRepair }
                val deviceName = pairingDeviceName(android.os.Build.MODEL) {
                    Settings.Global.getString(getApplication<Application>().contentResolver, Settings.Global.DEVICE_NAME)
                }
                val claim = bootstrap.claim(invitation, deviceName,
                    confirmPermissions = invitation.phoneConfirmation && pairingPreview != null,
                    repairProof = previous?.let { pairingRepairProof(it, invitation, "phone") },
                    rotate = known?.origin != bootstrapOrigin,
                    installationId = store.installationId().takeIf { bootstrap.supportsInstallationId })
                val recognized = previous != null && claim.optString("server_proof") == pairingRepairProof(previous, invitation, "desktop")
                require(!claim.has("server_proof") || recognized)
                if (generation != current) return@launch
                if (!invitation.phoneConfirmation) awaitingDesktop = true
                pairingStatus = text(R.string.pairing_finishing)
                while (System.currentTimeMillis() / 1000.0 < claim.getDouble("expires_at")) {
                    currentCoroutineContext().ensureActive()
                    val result = bootstrap.collect(invitation.id, claim.getString("pickup_secret"))
                    if (generation != current) return@launch
                    when (result.getString("status")) {
                        "denied" -> throw PairingFailure(PairingFailure.Reason.DENIED)
                        "approved" -> {
                            val reused = result.optBoolean("reused")
                            require(!reused || (recognized && known?.origin == bootstrapOrigin))
                            val credential = if (reused) requireNotNull(previous) else result.getString("token")
                            require(credential.isNotEmpty())
                            val saved = Connection(Backend.parse(invitation.origin, BuildConfig.DEBUG).origin.toString(),
                                credential, nodeToken = if (recognized) known?.nodeToken.orEmpty() else "", clientProtocol = 1, previousToken = if (recognized && !reused) previous.orEmpty() else "",
                                previousOrigin = if (recognized && !reused) known?.origin.orEmpty() else "",
                                origins = invitation.origins, tls = invitation.tls, previousTLS = known?.tls, previousOrigins = known?.origins.orEmpty(),
                                relay = invitation.relay ?: known?.relay)
                            val name = desktopName ?: target?.name ?: defaultDesktopName(saved.origin)
                            val desktop = target?.copy(name = name, connection = saved) ?: SavedDesktop.create(name, saved)
                            var updated = desktops.upserting(desktop)
                            // With nothing connected the new desktop must be the one the reconnect screen offers.
                            if (!connected) updated = updated.copy(activeId = desktop.id)
                            persist(updated)
                            if (!connected) { origin = saved.origin; canReconnect = true }
                            try { activate(desktop.id) }
                            catch (failure: BackendClient.HttpFailure) {
                                // The generic handler forgets the active desktop, which may still be another one.
                                if (failure.code != 401 || desktops.activeId == desktop.id) throw failure
                                removeDesktop(desktop.id)
                                error = text(R.string.desktop_access_revoked, desktop.name)
                                pairingInvitation = null
                                busy = false; awaitingDesktop = false; pairingStatus = null
                                return@launch
                            }
                            pairingVersion++
                            pairingInvitation = null
                            busy = false; awaitingDesktop = false; pairingStatus = null
                            return@launch
                        }
                        "pending" -> {
                            if (invitation.phoneConfirmation) throw PairingFailure(PairingFailure.Reason.INCOMPATIBLE)
                            delay(1000)
                        }
                        else -> throw PairingFailure(PairingFailure.Reason.INVALID)
                    }
                }
                throw PairingFailure(PairingFailure.Reason.EXPIRED)
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) {
                if (generation == current) { pairingInvitation = null; handle(failure) }
            } finally {
                bootstrap.close()
                if (generation == current) { busy = false; awaitingDesktop = false; pairingStatus = null }
            }
        }
    }

    /**
     * Connects to a saved desktop and only then makes it the active one, so a desktop that cannot be
     * reached never tears down the session already open.
     */
    private suspend fun activate(id: String) {
        connectionUpgrade.cancel()
        var saved = requireNotNull(desktops.desktop(id)).connection
        var viaRelay = false
        reconnectStage = 0
        reconnectStatus = text(R.string.reconnect_finding)
        val relay = saved.relay
        val route = resolveConnectionRoute(listOf(saved.origin) + saved.origins, relay != null) { route ->
            val probe = when (route) {
                is ConnectionRoute.Direct -> BackendClient(Backend.parse(route.origin, BuildConfig.DEBUG), "", probeOnly = true, deviceTrust = saved.tls)
                ConnectionRoute.Relay -> relayClient(requireNotNull(relay), "", probeOnly = true)
            }
            try { probe.capabilities() } finally { probe.close() }
        }
        when (route) {
            is ConnectionRoute.Direct -> saved = saved.copy(origin = route.origin)
            ConnectionRoute.Relay -> viaRelay = true
        }
        require(saved.clientProtocol == 1)
        reconnectStage = 2
        reconnectStatus = text(R.string.reconnect_verifying)
        val candidate = saved.relay?.takeIf { viaRelay }?.let { relayClient(it, saved.hostToken) }
            ?: BackendClient(Backend.parse(saved.origin, BuildConfig.DEBUG), saved.hostToken, deviceTrust = saved.tls)
        try {
            if (saved.previousToken.isNotEmpty()) {
                try { candidate.confirmPairing() }
                catch (failure: BackendClient.HttpFailure) {
                    if (failure.code != 401) throw failure
                    currentCoroutineContext().ensureActive()
                    val restored = saved.copy(origin = saved.previousOrigin.ifEmpty { saved.origin }, hostToken = saved.previousToken, previousToken = "", previousOrigin = "", tls = saved.previousTLS, previousTLS = null, origins = saved.previousOrigins, previousOrigins = emptyList())
                    persist(desktops.updating(id, restored))
                    candidate.close(); activate(id); return
                }
                val confirmed = saved.copy(previousToken = "", previousOrigin = "", previousTLS = null, previousOrigins = emptyList())
                currentCoroutineContext().ensureActive()
                persist(desktops.updating(id, confirmed))
                saved = confirmed
            } else {
                // A grant replacing a forgotten one stays provisional until confirmed, so activation
                // must not succeed without it. Confirming a finalized grant is a no-op.
                candidate.confirmPairing()
            }
            candidate.capabilities()
            val session = candidate.session()
            reconnectStage = 3
            reconnectStatus = text(R.string.reconnect_syncing)
            val navigation = candidate.initialNavigation()
            val taskList = candidate.scheduledTasks()
            val initialChat = candidate.composer()
            currentCoroutineContext().ensureActive()
            if (desktops.desktop(id) == null) throw CancellationException("desktop forgotten")
            if (id != desktops.activeId || connected) resetSession()
            // A desktop that switched its relay on (or reset it) since pairing hands over the new route.
            if (candidate.sessionRelay != null && candidate.sessionRelay != saved.relay) saved = saved.copy(relay = candidate.sessionRelay)
            var updated = desktops.updating(id, saved).copy(activeId = id)
            session.desktopName?.takeIf { it.isNotBlank() }?.let { updated = updated.renaming(id, it) }
            persist(updated); origin = saved.origin; canReconnect = true
            client?.close()
            client = candidate
            device = session
            attachmentsSupported = candidate.supportsAttachments
            applyNavigation(navigation)
            scheduledTasks = taskList
            selected = initialChat
            restoreModel(initialChat)
            connected = true
            if (viaRelay) startDirectUpgrade(id, saved, candidate)
        } catch (failure: Exception) { candidate.close(); throw failure }
    }

    private fun startDirectUpgrade(id: String, saved: Connection, relayed: BackendClient) {
        val deviceId = device?.id
        connectionUpgrade.start(
            prepare = {
                val route = resolveConnectionRoute(listOf(saved.origin) + saved.origins, false) { route ->
                    val origin = (route as ConnectionRoute.Direct).origin
                    val probe = BackendClient(Backend.parse(origin, BuildConfig.DEBUG), "", probeOnly = true, deviceTrust = saved.tls)
                    try { probe.capabilities() } finally { probe.close() }
                } as ConnectionRoute.Direct
                val direct = BackendClient(Backend.parse(route.origin, BuildConfig.DEBUG), saved.hostToken, deviceTrust = saved.tls)
                try {
                    withTimeout(5000) {
                        direct.capabilities()
                        check(direct.session().id == deviceId)
                    }
                    direct
                } catch (failure: Exception) { direct.close(); throw failure }
            },
            isCurrent = {
                foreground && connected && !isDemo && desktops.activeId == id &&
                    client === relayed && connection?.hostToken == saved.hostToken
            },
            isIdle = { !busy && !streaming && !voice.active && !approvalBusy && !stopInFlight && checkingDesktop == null },
            validate = { direct ->
                withTimeout(5000) { check(direct.session().id == deviceId) }
            },
            install = { direct ->
                val latest = requireNotNull(desktops.desktop(id)).connection
                val updated = latest.copy(origin = direct.backend.origin.toString())
                persist(desktops.updating(id, updated))
                origin = updated.origin
                retiredClients.add(relayed)
                client = direct
            },
            discard = { it.close() },
        )
    }

    fun connect() {
        if (isDemo) return
        val id = desktops.activeId ?: return
        if (busy || !canReconnect) return
        busy = true
        reconnecting = true
        error = null
        reconnectJob = viewModelScope.launch {
            try { withTimeout(20_000) { activate(id) } }
            catch (_: TimeoutCancellationException) { error = text(R.string.reconnect_unreachable) }
            catch (failure: CancellationException) { throw failure }
            catch (failure: java.io.IOException) {
                if (failure is BackendClient.HttpFailure || failure is javax.net.ssl.SSLException) handle(failure)
                else error = text(R.string.reconnect_unreachable)
            }
            catch (failure: Exception) { handle(failure) }
            finally { busy = false; reconnecting = false; reconnectStatus = null; reconnectStage = 0; reconnectJob = null }
        }
    }

    fun cancelReconnect() { reconnectJob?.cancel() }

    private fun handle(failure: Exception, fallback: Int = R.string.request_error) {
        if (failure is BackendClient.HttpFailure && failure.code == 401) {
            forget()
            error = text(R.string.access_revoked)
        } else if (failure is PairingFailure) {
            error = text(when (failure.reason) {
                PairingFailure.Reason.INVALID -> R.string.pairing_invalid
                PairingFailure.Reason.INCOMPATIBLE -> R.string.pairing_incompatible
                PairingFailure.Reason.EXPIRED -> R.string.pairing_expired
                PairingFailure.Reason.DENIED -> R.string.pairing_denied
                PairingFailure.Reason.SECURE_CONNECTION -> R.string.pairing_secure_connection
                PairingFailure.Reason.UNREACHABLE -> R.string.pairing_unreachable
            })
        } else { error = text(fallback) }
    }

    suspend fun watchNavigation() {
        while (currentCoroutineContext().isActive && connected) {
            if (foreground && !busy) refreshNow(poll = true)
            delay(10000)
        }
    }

    fun refresh(): Job = viewModelScope.launch { refreshNow() }

    private suspend fun refreshNow(poll: Boolean = false) {
        val api = client ?: return
        val current = generation
        try {
            val session = api.session()
            val scopeChanged = device?.permissions?.allChats != session.permissions.allChats || device?.permissions?.chatIds != session.permissions.chatIds
            refreshNavigation(api, poll && !scopeChanged)
            val taskList = api.scheduledTasks()
            if (current != generation) return
            device = session
            attachmentsSupported = api.supportsAttachments
            scheduledTasks = taskList
            val id = selected?.id
            if (!id.isNullOrEmpty() && !streaming) {
                val chat = api.chat(id)
                if (current == generation && selected?.id == id && !streaming) {
                    selected = chat
                    if (chatVisible && foreground) clearUnread(api, id)
                    if (chat.isRegent) {
                        if (regentVisible && (chat.regent?.unread ?: 0) > 0) api.markRead(id)
                        if (current == generation && selected?.id == id && chat.running && liveParts.isEmpty()) observe(id)
                    }
                }
            }
        } catch (error: CancellationException) { throw error }
        catch (failure: Exception) {
            if (BuildConfig.DEBUG) {
                val status = failure.message?.takeIf { it.matches(Regex("HTTP [0-9]{3}")) }
                android.util.Log.d("SuzentNetwork", "Refresh failure: ${failure.javaClass.simpleName} / ${status ?: failure.cause?.javaClass?.simpleName ?: "transport"}")
            }
            if (current == generation) handle(failure, R.string.refresh_error)
        }
    }

    /** Desktop counts each finished turn as unread until someone views the conversation. */
    private suspend fun clearUnread(api: MobileClient, id: String) {
        if (chats.none { it.id == id && it.unread > 0 && !it.isRegent }) return
        try { api.markRead(id) }
        catch (failure: CancellationException) { throw failure }
        catch (_: Exception) { return }
        chats = chats.map { if (it.id == id) it.copy(unread = 0) else it }
    }

    fun manageChat(chat: Chat, action: String, value: String? = null) {
        val api = client ?: return
        if (busy || device?.permissions?.manageChats != true) return
        busy = true
        val current = generation
        viewModelScope.launch {
            try {
                api.manageChat(chat.id, action, value)
                if (generation != current) return@launch
                if (action == "delete") {
                    drafts.remove(chat.id)
                    chats = chats.filterNot { it.id == chat.id }
                    if (selected?.id == chat.id) {
                        streamJob?.cancel(); api.cancelLive()
                        selected = null; streaming = false
                        liveParts = emptyList(); pendingApprovals = emptyList(); draft = ""; discardAttachments()
                    }
                }
                refreshNavigation(api, false)
                if (generation != current) return@launch
                val listing = chats
                if (action == "pin" && listing.any { it.id == chat.id && it.pinned }) pinnedVersion++
                listing.firstOrNull { it.id == selected?.id }?.let { updated ->
                    selected = selected?.copy(title = updated.title, projectId = updated.projectId, projectName = updated.projectName, pinned = updated.pinned)
                }
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { if (generation == current) handle(failure) }
            finally { busy = false }
        }
    }

    fun open(chat: Chat) {
        if (busy) return
        voice.stop()
        selected?.id?.let { drafts[it] = draft }
        generation++
        client?.cancelLive()
        streamJob?.cancel()
        streaming = false
        pendingApprovals = emptyList()
        if (chat.id != selected?.id) discardAttachments()
        selected = if (selected?.id == chat.id) selected else chat
        openingChatId = chat.id
        val openingGeneration = generation
        selectedModel = modelPreferences.getString("chatModel.$origin.${chat.id}", null)
        draft = drafts[chat.id].orEmpty()
        liveParts = emptyList()
        viewModelScope.launch {
            try {
                val api = client ?: return@launch
                val current = openingGeneration
                val saved = api.chat(chat.id)
                if (current == generation && selected?.id == chat.id) {
                    selected = saved
                    if (saved.isRegent) api.markRead(saved.id) else clearUnread(api, saved.id)
                    if (current != generation || selected?.id != saved.id) return@launch
                    restoreModel(saved)
                    openedVersion++
                    chats = chats.map { if (it.id == saved.id) saved.copy(messages = emptyList(), unread = 0) else it }
                    if (saved.running) observe(chat.id)
                }
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { if (openingGeneration == generation) handle(failure) }
            finally { if (openingGeneration == generation) openingChatId = null }
        }
    }

    fun messageAction(message: DisplayMessage, action: String, text: String? = null) {
        val api = client ?: return
        val id = selected?.id?.takeIf { it.isNotEmpty() } ?: return
        if (busy || streaming) return
        busy = true
        viewModelScope.launch {
            try {
                val target = api.messageAction(id, message.messageIndex, action, text, selectedModel)
                val chat = api.chat(target)
                busy = false
                open(chat)
                refreshNow()
            } catch (failure: Exception) { handle(failure) }
            finally { busy = false }
        }
    }

    fun selectModel(model: String?) {
        selectedModel = model
        modelPreferences.edit().putString("lastModel.$origin", model).apply()
        selected?.id?.takeIf { it.isNotEmpty() }?.let { id ->
            modelPreferences.edit().putString("chatModel.$origin.$id", model).apply()
        }
    }

    private fun restoreModel(chat: Chat) {
        val key = if (chat.id.isEmpty()) "lastModel.$origin" else "chatModel.$origin.${chat.id}"
        val remembered = modelPreferences.getString(key, null)
        selectedModel = remembered?.takeIf { it in chat.models }
        // Once the backend acknowledges a pending choice, let future desktop changes win.
        if (chat.id.isNotEmpty() && (remembered == chat.model || selectedModel == null)) {
            modelPreferences.edit().remove(key).apply()
            selectedModel = null
        }
    }

    fun create(projectId: String? = null) {
        val api = client ?: return
        if (busy || device?.permissions?.createChats != true) return
        voice.stop()
        val current = generation
        busy = true
        viewModelScope.launch {
            try {
                selected?.id?.let { drafts[it] = draft }
                val composer = api.composer()
                if (current != generation) return@launch
                generation++
                api.cancelLive()
                streamJob?.cancel()
                streamJob = null
                streaming = false
                pendingApprovals = emptyList(); approvalChoices = emptyMap()
                liveParts = emptyList()
                selected = if (projectId == null) composer else composer.copy(projectId = projectId, projectName = projects.firstOrNull { it.id == projectId }?.name)
                restoreModel(composer)
                draft = ""
                discardAttachments()
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { handle(failure) }
            finally { busy = false }
        }
    }

    fun attach(uris: List<Uri>) {
        val room = MAX_ATTACHMENTS - attachments.size
        if (uris.isEmpty() || busy) return
        if (room <= 0) { error = text(R.string.attachment_limit, MAX_ATTACHMENTS); return }
        if (uris.size > room) error = text(R.string.attachment_limit, MAX_ATTACHMENTS)
        val context = getApplication<Application>()
        viewModelScope.launch {
            try {
                val copied = withContext(Dispatchers.IO) { uris.take(room).map { AttachmentFiles.copy(context, it) } }
                attachments = (attachments + copied).take(MAX_ATTACHMENTS)
            } catch (failure: CancellationException) { throw failure }
            catch (_: Exception) { error = text(R.string.attachment_read_error) }
        }
    }

    fun attachCaptured(attachment: PendingAttachment) {
        if (attachments.size >= MAX_ATTACHMENTS) { attachment.file.delete(); error = text(R.string.attachment_limit, MAX_ATTACHMENTS); return }
        attachments = attachments + attachment
    }

    fun removeAttachment(attachment: PendingAttachment) {
        attachments = attachments - attachment
        attachment.file.delete()
    }

    private fun discardAttachments() {
        attachments.forEach { it.file.delete() }
        attachments = emptyList()
    }

    fun send() = submit(draft.trim(), attachments, fromDraft = true)

    val surfacesSupported: Boolean get() = client?.supportsSurfaces == true

    /**
     * A button or form on a surface: a blocked question gets its answer, anything else is sent like a message.
     * [done] reports whether it was delivered, so a form can be used again after a failure.
     */
    fun act(surface: A2UISurface, action: String, context: Map<String, Any?>, done: (Boolean) -> Unit = {}) {
        val api = client ?: return done(false)
        val id = selected?.id?.takeIf { it.isNotEmpty() } ?: return done(false)
        if (device?.permissions?.send != true) return done(false)
        if (surface.deferred) {
            val current = generation
            viewModelScope.launch {
                try {
                    api.answerSurface(id, surface.id, deferredAnswer(context))
                    liveParts = liveParts.filterNot { it.type == "a2ui" && it.surface?.id == surface.id }
                    done(true)
                } catch (failure: CancellationException) { throw failure }
                catch (failure: Exception) { if (current == generation) handle(failure, R.string.surface_answer_failed); done(false) }
            }
            return
        }
        val text = if (action == "submit_question") questionAnswerText(context) else canvasActionMessage(action, context, surface.id)
        if (text.isNotEmpty()) submit(text, emptyList(), fromDraft = false, done) else done(false)
    }

    private fun submit(message: String, outgoing: List<PendingAttachment>, fromDraft: Boolean, done: (Boolean) -> Unit = {}) {
        val api = client ?: return done(false)
        var id = selected?.id ?: return done(false)
        if (busy || streaming || (message.isEmpty() && outgoing.isEmpty()) || device?.permissions?.send != true) return done(false)
        var delivered = false
        busy = true
        error = null
        val current = generation
        viewModelScope.launch {
            try {
                if (id.isEmpty()) {
                    if (device?.permissions?.createChats != true) return@launch
                    val created = api.create(text(R.string.mobile_conversation), selected?.projectId)
                    if (current != generation) return@launch
                    selected = created
                    id = created.id
                    modelPreferences.edit().putString("chatModel.$origin.$id", selectedModel).apply()
                    chats = listOf(created) + chats
                }
                val issued = if (outgoing.isEmpty()) emptyList() else api.upload(id, outgoing)
                if (current != generation) return@launch
                api.send(id, message, selectedModel, issued)
                if (current != generation) return@launch
                if (fromDraft) { draft = ""; drafts.remove(id) }
                outgoing.forEach { it.file.delete() }
                attachments = attachments - outgoing.toSet()
                sentVersion++
                selected?.takeIf { it.id == id }?.let { chat ->
                    selected = chat.copy(running = true, messages = chat.messages + ChatMessage("user", message,
                        files = outgoing.map { FileAttachment(it.name, it.mimeType) }))
                }
                chats = chats.map { if (it.id == id) it.copy(running = true) else it }
                delivered = true
                if (foreground) observe(id)
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { if (current == generation) handle(failure, R.string.send_unknown) }
            finally { if (current == generation) { busy = false; pairingStatus = null }; done(delivered) }
        }
    }

    private fun observe(id: String) {
        val api = client ?: return
        if (streaming || !foreground) return
        val current = generation
        streaming = true
        liveParts = emptyList()
        streamJob = viewModelScope.launch {
            val buffer = LiveActivityBuffer()
            fun publishActivity() { buffer.drain()?.let { liveParts = it } }
            val publisher = launch {
                while (isActive) {
                    delay(50)
                    if (current == generation && foreground) publishActivity()
                }
            }
            try {
                // The local demo owns main-thread state; the network client can collect
                // into the synchronized buffer without a UI-thread hop for every token.
                withContext(if (api is DemoClient) Dispatchers.Main.immediate else Dispatchers.Default) {
                    api.observe(id) { event ->
                        buffer.consume(event)
                        if (event.optString("type") == "RUN_ERROR") withContext(Dispatchers.Main) {
                            if (current == generation && foreground) error = text(R.string.task_error)
                        }
                    }
                }
                publisher.cancel()
                if (current == generation && foreground) publishActivity()
                val saved = api.chat(id)
                if (current == generation && selected?.id == id) {
                    selected = saved
                    chats = chats.map { if (it.id == saved.id) saved.copy(messages = emptyList(), unread = it.unread) else it }
                    liveParts = emptyList()
                }
            } catch (error: CancellationException) { throw error }
            catch (failure: Exception) { if (current == generation && foreground) handle(failure, R.string.stream_error) }
            finally {
                publisher.cancel()
                if (current == generation) {
                    if (foreground) publishActivity()
                    streaming = false
                }
            }
        }
    }

    suspend fun watchApprovals(id: String) {
        if (id.isEmpty()) return
        pendingApprovals = emptyList(); approvalChoices = emptyMap()
        val current = generation
        var previousRunning = false
        var previousPending = false
        while (currentCoroutineContext().isActive && selected?.id == id && generation == current) {
            if (foreground && !approvalBusy) {
                try {
                    val api = client ?: return
                    val state = api.approvals(id)
                    currentCoroutineContext().ensureActive()
                    if (selected?.id != id || generation != current) return
                    if (!approvalBusy) {
                        if (state.pending != pendingApprovals) approvalChoices = emptyMap()
                        pendingApprovals = state.pending
                    }
                    if (state.running && !streaming) observe(id)
                    if (!state.running && !streaming && liveParts.isEmpty() && (previousRunning || previousPending && state.pending.isEmpty())) {
                        val saved = api.chat(id)
                        if (selected?.id == id && generation == current) { selected = saved; liveParts = emptyList() }
                    }
                    previousRunning = state.running; previousPending = state.pending.isNotEmpty()
                } catch (failure: CancellationException) { throw failure }
                catch (failure: Exception) {
                    if (failure is BackendClient.HttpFailure && failure.code in listOf(401, 403)) { pendingApprovals = emptyList(); handle(failure); return }
                    if (failure is BackendClient.HttpFailure && failure.code == 404) return
                }
            }
            delay(2500)
        }
    }

    fun chooseApproval(item: ApprovalRequest, action: ApprovalAction) {
        val id = selected?.id ?: return
        val api = client ?: return
        if (approvalBusy || device?.permissions?.approveTools != true || item !in pendingApprovals || action !in item.actions) return
        approvalChoices = approvalChoices + (item.id to action.id)
        if (!pendingApprovals.all { approvalChoices.containsKey(it.id) }) return
        val pending = pendingApprovals
        val choices = approvalChoices
        val current = generation
        approvalBusy = true
        viewModelScope.launch {
            try {
                api.decideApprovals(id, pending, choices)
                if (current == generation && selected?.id == id) {
                    pendingApprovals = emptyList()
                    if (pending.all { it.kind == "tool" }) observe(id)
                }
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { if (current == generation) handle(failure, R.string.approval_refresh) }
            finally { if (current == generation) { approvalBusy = false; approvalChoices = emptyMap() } }
        }
    }

    var stopInFlight by mutableStateOf(false)
        private set

    fun stop() {
        if (stopInFlight || device?.permissions?.stop != true) return
        val api = client ?: return
        val id = selected?.id ?: return
        stopInFlight = true
        viewModelScope.launch {
            try { api.stop(id) } catch (failure: Exception) { handle(failure) }
            finally { stopInFlight = false }
        }
    }

    fun setForeground(active: Boolean) {
        foreground = active
        if (!active) {
            connectionUpgrade.cancel()
            voice.stop()
            cancelReconnect()
            client?.cancelLive()
            streamJob?.cancel()
            streaming = false
            liveParts = emptyList()
            disconnectNode()
        } else {
            val relayed = client as? BackendClient
            val saved = connection
            val id = desktops.activeId
            if (relayed?.relay != null && saved != null && id != null) startDirectUpgrade(id, saved, relayed)
            if (!connected && canReconnect) connect()
            viewModelScope.launch {
                refreshNow()
                selected?.takeIf { it.running }?.let { chat -> observe(chat.id) }
                if (nodeEnabled && foreground) startNode()
            }
        }
    }

    fun toggleNode(enabled: Boolean) {
        if (isDemo) return
        nodeEnabled = enabled
        if (enabled && foreground) startNode() else disconnectNode()
    }

    private fun disconnectNode() {
        socket?.let { (client as? BackendClient)?.cancelNode(it) }
        socket = null
        nodeStatus = text(if (nodeEnabled) R.string.node_offline else R.string.node_off)
    }

    private fun startNode() {
        if (isDemo) return
        disconnectNode()
        val api = client as? BackendClient ?: return
        val saved = connection ?: return
        val desktopId = desktops.activeId ?: return
        nodeStatus = text(R.string.node_connecting)
        socket = api.node(object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                viewModelScope.launch {
                    if (socket !== webSocket || !foreground) { api.cancelNode(webSocket); return@launch }
                    webSocket.send(NodeProtocol.connect("Suzent Android", "android", saved.nodeToken).toString())
                }
            }
            override fun onMessage(webSocket: WebSocket, text: String) {
                viewModelScope.launch {
                    if (socket !== webSocket || !foreground) return@launch
                    try {
                        val message = JSONObject(text)
                        when (message.optString("type")) {
                            "pending" -> nodeStatus = text(R.string.node_pending, message.optString("pairing_code"))
                            "connected" -> {
                                val credential = message.optString("device_token")
                                if (credential.isNotEmpty()) {
                                    desktops.desktop(desktopId)?.let { persist(desktops.updating(desktopId, it.connection.copy(nodeToken = credential))) }
                                }
                                nodeStatus = text(R.string.node_online)
                            }
                            "error" -> { disconnectNode(); nodeStatus = text(R.string.node_error) }
                            else -> NodeProtocol.reply(message, "android")?.let { webSocket.send(it.toString()) }
                        }
                    } catch (_: Exception) { disconnectNode(); nodeStatus = text(R.string.node_error) }
                }
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                viewModelScope.launch {
                    if (socket === webSocket) { disconnectNode(); nodeStatus = text(R.string.node_error) }
                }
            }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, null)
                viewModelScope.launch {
                    if (socket === webSocket) { disconnectNode(); nodeStatus = text(R.string.node_error) }
                }
            }
        })
    }

    /** Keeps the current desktop open until the other one answers; a desktop that cannot be reached is reported, not switched to. */
    fun switchDesktop(id: String) {
        val desktop = desktops.desktop(id) ?: return
        if (isDemo || streaming || checkingDesktop != null) return
        if (id == desktops.activeId && connected) return
        if (!connected) {
            // Nothing open to protect: abandon the reconnect in progress and try this desktop instead.
            viewModelScope.launch {
                // A second tap must also cancel the attempt the first tap started, or two desktops race.
                while (true) { val pending = reconnectJob ?: break; pending.cancel(); pending.join() }
                if (busy || connected) return@launch
                persist(desktops.copy(activeId = id)); origin = desktop.connection.origin
                canReconnect = desktop.connection.clientProtocol == 1
                connect()
            }
            return
        }
        if (busy) return
        checkingDesktop = id
        error = null
        switchJob = viewModelScope.launch {
            try { withTimeout(20_000) { activate(id) } }
            catch (_: TimeoutCancellationException) { error = text(R.string.desktop_unreachable, desktop.name) }
            catch (failure: CancellationException) { throw failure }
            catch (failure: BackendClient.HttpFailure) {
                if (failure.code == 401) { removeDesktop(id); error = text(R.string.desktop_access_revoked, desktop.name) }
                else error = text(R.string.desktop_unreachable, desktop.name)
            }
            catch (_: Exception) { error = text(R.string.desktop_unreachable, desktop.name) }
            finally { checkingDesktop = null; switchJob = null }
        }
    }

    fun forget() { desktops.activeId?.let(::forgetDesktop) ?: exitDemo() }

    /** Forgetting the open desktop moves on to the next saved one, if any. */
    fun forgetDesktop(id: String) {
        if (isDemo) { exitDemo(); return }
        desktops.desktop(id)?.let { revokeOnDesktop(it.connection) }
        // A switch still checking this desktop would otherwise activate an id that is no longer saved.
        if (checkingDesktop == id) switchJob?.cancel()
        if (id != desktops.activeId) { removeDesktop(id); return }
        switchJob?.cancel()
        removeDesktop(id)
        clearSession()
        if (canReconnect) connect()
    }

    /** Best effort: otherwise the desktop keeps a grant no phone holds, and the next scan adds another. */
    private fun revokeOnDesktop(saved: Connection) {
        viewModelScope.launch {
            val revoker = try { BackendClient(Backend.parse(saved.origin, BuildConfig.DEBUG), saved.hostToken, deviceTrust = saved.tls) }
                catch (_: Exception) { return@launch }
            try { revoker.forgetPairing() } catch (failure: CancellationException) { throw failure } catch (_: Exception) { }
            finally { revoker.close() }
        }
    }

    private fun removeDesktop(id: String) {
        try { persist(desktops.removing(id)) } catch (_: Exception) { error = text(R.string.secure_error) }
    }

    private fun persist(value: SavedDesktops) {
        desktops = value
        store.save(value)
    }

    /** Drops everything that belongs to the open desktop's session; credentials stay. */
    private fun resetSession() {
        connectionUpgrade.cancel()
        retiredClients.forEach { it.close() }
        retiredClients.clear()
        voice.stop()
        scheduledTasks = emptyList()
        projects = emptyList(); selectedModel = null; drafts.clear(); discardAttachments(); attachmentsSupported = false
        pendingApprovals = emptyList(); approvalChoices = emptyMap(); approvalBusy = false
        generation++
        nodeEnabled = false
        disconnectNode()
        streamJob?.cancel()
        client?.close()
        client = null
        connected = false
        selected = null
        chats = emptyList()
        chatPages = emptyMap(); loadingPages = emptySet(); navigationRevision++
        device = null
        draft = ""
        streaming = false
        liveParts = emptyList()
    }

    private fun clearSession() {
        pairingJob?.cancel()
        reconnectJob?.cancel()
        resetSession()
        busy = false
        canReconnect = connection?.clientProtocol == 1
        pairingInvitation = null
        awaitingDesktop = false
        invitationText = ""
        origin = connection?.origin.orEmpty()
    }

    override fun onCleared() {
        connectionUpgrade.cancel()
        retiredClients.forEach { it.close() }
        retiredClients.clear()
        voice.stop(); disconnectNode(); client?.close()
    }
}
