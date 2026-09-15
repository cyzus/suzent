package com.suzent.mobile

import android.app.Application
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
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

class MobileModel(application: Application) : AndroidViewModel(application) {
    var origin by mutableStateOf("")
    var invitationText by mutableStateOf("")
    var pairingInvitation by mutableStateOf<PairingInvitation?>(null)
    var pairingPreview by mutableStateOf<PairingPreview?>(null)
    var pairingCode by mutableStateOf<String?>(null)
    var device by mutableStateOf<ClientDevice?>(null)
    var canReconnect by mutableStateOf(false)
    private var pairingJob: Job? = null
    var chats by mutableStateOf<List<Chat>>(emptyList())
    var selected by mutableStateOf<Chat?>(null)
    var draft by mutableStateOf("")
    var liveParts by mutableStateOf<List<MessagePart>>(emptyList())
    var pendingApprovals by mutableStateOf<List<ApprovalRequest>>(emptyList())
    var approvalChoices by mutableStateOf<Map<String, String>>(emptyMap())
    var approvalBusy by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var busy by mutableStateOf(false)
    var streaming by mutableStateOf(false)
    var connected by mutableStateOf(false)
    var nodeEnabled by mutableStateOf(false)
    var nodeStatus by mutableStateOf(text(R.string.node_off))
    private val store = CredentialStore(application)
    private var connection: Connection? = null
    private var client: BackendClient? = null
    private var streamJob: Job? = null
    private var socket: WebSocket? = null
    private var foreground = false
    private var generation = 0

    private fun text(id: Int, vararg args: Any): String = getApplication<Application>().getString(id, *args)

    init {
        try {
            connection = store.load()
            origin = connection?.origin.orEmpty()
            canReconnect = connection?.clientProtocol == 1
        } catch (_: Exception) { error = text(R.string.secure_error) }
    }

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
        pairingJob = viewModelScope.launch {
            try {
                val selected = resolvePairingInvitation(invitation) { origin ->
                    val probe = BackendClient(Backend.parse(origin, BuildConfig.DEBUG), "", probeOnly = true)
                    try {
                        probe.capabilities()
                        if (invitation.phoneConfirmation) probe.pairingPreview(invitation) else null
                    } finally { probe.close() }
                }
                if (current == generation) { pairingPreview = selected.second; pairingInvitation = selected.first }
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { if (current == generation) handle(failure) }
            finally { if (current == generation) busy = false }
        }
    }

    fun cancelPairing() {
        pairingJob?.cancel()
        pairingJob = null
        pairingInvitation = null
        pairingCode = null
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
        pairingJob = viewModelScope.launch {
            val bootstrap = BackendClient(Backend.parse(invitation.origin, BuildConfig.DEBUG), "")
            try {
                bootstrap.capabilities()
                val claim = bootstrap.claim(invitation, android.os.Build.MODEL,
                    confirmPermissions = invitation.phoneConfirmation && pairingPreview != null)
                if (generation != current) return@launch
                if (!invitation.phoneConfirmation) pairingCode = invitation.id.take(6)
                while (System.currentTimeMillis() / 1000.0 < claim.getDouble("expires_at")) {
                    currentCoroutineContext().ensureActive()
                    val result = bootstrap.collect(invitation.id, claim.getString("pickup_secret"))
                    if (generation != current) return@launch
                    when (result.getString("status")) {
                        "denied" -> throw PairingFailure(PairingFailure.Reason.DENIED)
                        "approved" -> {
                            val credential = result.getString("token")
                            require(credential.isNotEmpty())
                            val saved = Connection(Backend.parse(invitation.origin, BuildConfig.DEBUG).origin.toString(),
                                credential, clientProtocol = 1)
                            store.save(saved)
                            connection = saved
                            origin = saved.origin
                            canReconnect = true
                            activate(saved)
                            pairingInvitation = null
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
                if (generation == current) { busy = false; pairingCode = null }
            }
        }
    }

    private suspend fun activate(saved: Connection) {
        require(saved.clientProtocol == 1)
        val candidate = BackendClient(Backend.parse(saved.origin, BuildConfig.DEBUG), saved.hostToken)
        try {
            candidate.capabilities()
            val session = candidate.session()
            val listing = candidate.chats()
            currentCoroutineContext().ensureActive()
            client?.close()
            client = candidate
            device = session
            chats = listing
            connected = true
        } catch (failure: Exception) { candidate.close(); throw failure }
    }

    fun connect() {
        val saved = connection ?: return
        if (busy || !canReconnect) return
        busy = true
        error = null
        viewModelScope.launch {
            try { activate(saved) }
            catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { handle(failure) }
            finally { busy = false }
        }
    }

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
                PairingFailure.Reason.UNREACHABLE -> R.string.pairing_unreachable
            })
        } else { error = text(fallback) }
    }

    fun refresh() { viewModelScope.launch { refreshNow() } }

    private suspend fun refreshNow() {
        val api = client ?: return
        val current = generation
        try {
            val session = api.session()
            val listing = api.chats()
            if (current != generation) return
            device = session
            chats = listing
            val id = selected?.id
            if (id != null && !streaming) {
                val chat = api.chat(id)
                if (current == generation && selected?.id == id) selected = chat
            }
            if (current == generation) error = null
        } catch (error: CancellationException) { throw error }
        catch (failure: Exception) {
            if (BuildConfig.DEBUG) {
                val status = failure.message?.takeIf { it.matches(Regex("HTTP [0-9]{3}")) }
                android.util.Log.d("SuzentNetwork", "Refresh failure: ${failure.javaClass.simpleName} / ${status ?: failure.cause?.javaClass?.simpleName ?: "transport"}")
            }
            if (current == generation) handle(failure, R.string.refresh_error)
        }
    }

    fun open(chat: Chat) {
        if (streaming || busy) return
        selected = chat
        liveParts = emptyList()
        viewModelScope.launch {
            try {
                val api = client ?: return@launch
                val current = generation
                val saved = api.chat(chat.id)
                if (current == generation && selected?.id == chat.id) {
                    selected = saved
                    chats = chats.map { if (it.id == saved.id) saved.copy(messages = emptyList()) else it }
                    if (saved.running) observe(chat.id)
                }
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { handle(failure) }
        }
    }

    fun create() {
        val api = client ?: return
        if (busy || streaming || device?.permissions?.createChats != true) return
        busy = true
        viewModelScope.launch {
            try {
                selected = api.create(text(R.string.mobile_conversation))
                refreshNow()
            } catch (failure: Exception) { handle(failure) }
            finally { busy = false }
        }
    }

    fun send() {
        val api = client ?: return
        val id = selected?.id ?: return
        val message = draft.trim()
        if (busy || streaming || message.isEmpty() || device?.permissions?.send != true) return
        busy = true
        error = null
        val current = generation
        viewModelScope.launch {
            try {
                api.send(id, message)
                if (current != generation) return@launch
                draft = ""
                selected?.takeIf { it.id == id }?.let { chat ->
                    selected = chat.copy(running = true, messages = chat.messages + ChatMessage("user", message))
                }
                chats = chats.map { if (it.id == id) it.copy(running = true) else it }
                if (foreground) observe(id)
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) { if (current == generation) handle(failure, R.string.send_unknown) }
            finally { if (current == generation) busy = false }
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
                api.observe(id) { event ->
                    withContext(Dispatchers.Main) {
                        if (current == generation && foreground) {
                            buffer.consume(event)
                            if (event.optString("type") == "RUN_ERROR") error = text(R.string.task_error)
                        }
                    }
                }
                publisher.cancel()
                if (current == generation && foreground) publishActivity()
                val saved = api.chat(id)
                if (current == generation && selected?.id == id) {
                    selected = saved
                    chats = chats.map { if (it.id == saved.id) saved.copy(messages = emptyList()) else it }
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

    fun stop() {
        if (device?.permissions?.stop != true) return
        val api = client ?: return
        val id = selected?.id ?: return
        viewModelScope.launch {
            try { api.stop(id) } catch (failure: Exception) { handle(failure) }
        }
    }

    fun setForeground(active: Boolean) {
        foreground = active
        if (!active) {
            client?.cancelLive()
            streamJob?.cancel()
            streaming = false
            liveParts = emptyList()
            disconnectNode()
        } else {
            viewModelScope.launch {
                refreshNow()
                selected?.takeIf { it.running }?.let { chat -> observe(chat.id) }
                if (nodeEnabled && foreground) startNode()
            }
        }
    }

    fun toggleNode(enabled: Boolean) {
        nodeEnabled = enabled
        if (enabled && foreground) startNode() else disconnectNode()
    }

    private fun disconnectNode() {
        socket?.cancel()
        socket = null
        nodeStatus = text(if (nodeEnabled) R.string.node_offline else R.string.node_off)
    }

    private fun startNode() {
        disconnectNode()
        val api = client ?: return
        val saved = connection ?: return
        nodeStatus = text(R.string.node_connecting)
        socket = api.node(object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                viewModelScope.launch {
                    if (socket !== webSocket || !foreground) { webSocket.cancel(); return@launch }
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
                                    val updated = saved.copy(nodeToken = credential)
                                    store.save(updated)
                                    connection = updated
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

    fun forget() {
        pairingJob?.cancel()
        pendingApprovals = emptyList(); approvalChoices = emptyMap(); approvalBusy = false
        try { store.clear() } catch (_: Exception) { error = text(R.string.secure_error) }
        generation++
        nodeEnabled = false
        disconnectNode()
        streamJob?.cancel()
        client?.close()
        client = null
        connection = null
        connected = false
        busy = false
        selected = null
        chats = emptyList()
        canReconnect = false
        device = null
        pairingInvitation = null
        pairingCode = null
        invitationText = ""
        origin = ""
        draft = ""
        streaming = false
        liveParts = emptyList()
    }

    override fun onCleared() { disconnectNode(); client?.close() }
}
