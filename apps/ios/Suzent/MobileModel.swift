import Foundation
import SwiftUI
import SuzentCore

@MainActor @Observable final class MobileModel {
    var origin = ""
    var invitationText = ""
    var pairingInvitation: PairingInvitation?
    var pairingPreview: PairingPreview?
    var pairingCode: String?
    var device: ClientDevice?
    var canReconnect = false
    private var pairingTask: Task<Void, Never>?
    var chats: [Chat] = []
    var selected: Chat?
    var draft = ""
    var liveParts: [MessagePart] = []
    var pendingApprovals: [ApprovalRequest] = []
    var approvalChoices: [String: String] = [:]
    var approvalBusy = false
    var liveText = ""
    var error: String?
    var busy = false
    var streaming = false
    @ObservationIgnored private var activityBuffer = LiveActivityBuffer()
    @ObservationIgnored private var liveTextDirty = false
    var connected = false
    var nodeEnabled = false
    var nodeStatus = String(localized: "Off")
    private var connection: Connection?
    private var client: SuzentClient?
    private var streamTask: Task<Void, Never>?
    private var nodeTask: Task<Void, Never>?
    private var socket: URLSessionWebSocketTask?
    private var generation = UUID()
    private var foreground = true

    init() {
        do {
            if let saved = try CredentialStore.load() {
                connection = saved
                origin = saved.origin
                canReconnect = saved.clientProtocol == 1
            }
        } catch { self.error = error.localizedDescription }
    }

    private var allowsHTTP: Bool {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }

    func stageInvitation(_ text: String) {
        guard !busy else { return }
        let invitation: PairingInvitation
        do { invitation = try PairingInvitation.parse(text, allowHTTP: allowsHTTP) }
        catch { handle(error); return }
        invitationText = ""
        pairingInvitation = nil
        pairingPreview = nil
        error = nil
        busy = true
        let current = generation
        let allowHTTP = allowsHTTP
        pairingTask = Task {
            defer { if generation == current { busy = false } }
            do {
                let selected = try await invitation.resolving { origin in
                    let probe = SuzentClient(backend: try Backend(origin, allowHTTP: allowHTTP), token: "", probeOnly: true)
                    defer { probe.close() }
                    _ = try await probe.capabilities()
                    if invitation.phoneConfirmation { _ = try await probe.pairingPreview(invitation) }
                }
                let preview: PairingPreview?
                if selected.phoneConfirmation {
                    let probe = SuzentClient(backend: try Backend(selected.origin, allowHTTP: allowHTTP), token: "", probeOnly: true)
                    defer { probe.close() }
                    preview = try await probe.pairingPreview(selected)
                } else { preview = nil }
                guard generation == current, !Task.isCancelled else { return }
                pairingPreview = preview
                pairingInvitation = selected
            } catch { if generation == current, !Task.isCancelled { handle(error) } }
        }
    }

    func cancelPairing() {
        pairingTask?.cancel()
        pairingTask = nil
        pairingInvitation = nil
        pairingCode = nil
        pairingPreview = nil
        busy = false
        generation = UUID()
    }

    func approveDestination() {
        guard let invitation = pairingInvitation, !busy else { return }
        busy = true
        error = nil
        let current = generation
        pairingTask = Task {
            defer { if generation == current { busy = false; pairingCode = nil } }
            do {
                let backend = try Backend(invitation.origin, allowHTTP: allowsHTTP)
                let bootstrap = SuzentClient(backend: backend, token: "")
                defer { bootstrap.close() }
                _ = try await bootstrap.capabilities()
                try Task.checkCancellation()
                let claim = try await bootstrap.claim(invitation, name: UIDevice.current.name,
                                                      confirmPermissions: invitation.phoneConfirmation && pairingPreview != nil)
                guard generation == current else { return }
                if !invitation.phoneConfirmation { pairingCode = String(invitation.pairingId.prefix(6)) }
                while Date().timeIntervalSince1970 < claim.expiresAt {
                    try Task.checkCancellation()
                    let result = try await bootstrap.collect(pairingID: invitation.pairingId, pickupSecret: claim.pickupSecret)
                    guard generation == current else { return }
                    if result.status == "denied" { throw PairingError.denied }
                    if result.status == "approved" {
                        guard let token = result.token, !token.isEmpty, result.device != nil else {
                            throw ClientError.invalidResponse
                        }
                        let saved = Connection(origin: backend.url.absoluteString, hostToken: token, clientProtocol: 1)
                        try CredentialStore.save(saved)
                        connection = saved
                        origin = saved.origin
                        canReconnect = true
                        try await activate(saved)
                        pairingInvitation = nil
                        return
                    }
                    guard result.status == "pending", !invitation.phoneConfirmation else { throw ClientError.invalidResponse }
                    try await Task.sleep(for: .seconds(1))
                }
                throw PairingError.expired
            } catch {
                if !Task.isCancelled, generation == current {
                    pairingInvitation = nil
                    handle(error)
                }
            }
        }
    }

    private func activate(_ saved: Connection) async throws {
        guard saved.clientProtocol == 1 else { throw PairingError.incompatible }
        let backend = try Backend(saved.origin, allowHTTP: allowsHTTP)
        let candidate = SuzentClient(backend: backend, token: saved.hostToken)
        do {
            _ = try await candidate.capabilities()
            let session = try await candidate.clientSession()
            let listing = try await candidate.chats()
            try Task.checkCancellation()
            client?.close()
            client = candidate
            device = session.device
            chats = listing
            connected = true
        } catch { candidate.close(); throw error }
    }

    func connect() async {
        guard let connection, canReconnect, !busy else { return }
        busy = true
        defer { busy = false }
        error = nil
        do { try await activate(connection) }
        catch { handle(error) }
    }

    private func handle(_ failure: Error) {
        if case ClientError.http(401) = failure {
            forget()
            error = String(localized: "Access was revoked or expired. Pair this phone again.")
        } else { error = failure.localizedDescription }
    }

    func refresh() async {
        guard let client else { return }
        let current = generation
        do {
            let session = try await client.clientSession()
            let listing = try await client.chats()
            guard generation == current else { return }
            device = session.device
            chats = listing
            if let id = selected?.id, !streaming {
                let chat = try await client.chat(id)
                guard generation == current, selected?.id == id else { return }
                selected = chat
            }
        } catch { if generation == current { handle(error) } }
    }

    func open(_ chat: Chat) async {
        guard let client, !streaming else { return }
        selected = chat
        liveText = ""; liveParts = []
        let current = generation
        do {
            let saved = try await client.chat(chat.id)
            guard current == generation, selected?.id == chat.id else { return }
            selected = saved
            syncRunning(saved)
            if saved.isRunning == true { observe(chat.id, client: client) }
        } catch { if current == generation { handle(error) } }
    }

    func createChat() async {
        guard let client, device?.permissions.createChats == true, !busy, !streaming else { return }
        busy = true
        defer { busy = false }
        do {
            let chat = try await client.createChat(title: String(localized: "Mobile conversation"))
            selected = chat
            await refresh()
        } catch { handle(error) }
    }

    func send() async {
        guard let client, device?.permissions.send == true, let id = selected?.id, !busy, !streaming else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        busy = true
        error = nil
        defer { busy = false }
        do {
            try await client.send(text, chatID: id)
            draft = ""
            if var chat = selected, chat.id == id {
                chat.messages = (chat.messages ?? []) + [ChatMessage(role: "user", content: text)]
                chat.isRunning = true
                selected = chat
                syncRunning(chat)
            }
            if foreground { observe(id, client: client) }
        } catch {
            if case ClientError.http(401) = error { handle(error) }
            else { self.error = String(localized: "Send could not be confirmed. Refresh history before sending again.") }
        }
    }

    private func observe(_ id: String, client: SuzentClient) {
        guard !streaming, foreground else { return }
        streaming = true
        liveText = ""; liveParts = []
        let current = generation
        activityBuffer = LiveActivityBuffer()
        liveTextDirty = false
        streamTask = Task {
            let publisher = Task { @MainActor in
                while !Task.isCancelled {
                    do { try await Task.sleep(for: .milliseconds(50)) } catch { return }
                    guard generation == current, foreground else { return }
                    flushLiveText()
                }
            }
            defer { publisher.cancel() }
            do {
                try await client.observe(id) { [weak self] event in
                    await self?.receive(event, generation: current)
                }
                publisher.cancel()
                guard generation == current, !Task.isCancelled else { return }
                flushLiveText()
                let saved = try await client.chat(id)
                guard generation == current, !Task.isCancelled, selected?.id == id else { return }
                selected = saved
                syncRunning(saved)
                liveText = ""; liveParts = []
            } catch {
                if !Task.isCancelled, generation == current { flushLiveText(); handle(error) }
            }
            guard generation == current, !Task.isCancelled else { return }
            streaming = false
        }
    }

    private func receive(_ event: StreamEvent, generation current: UUID) {
        guard generation == current, foreground else { return }
        activityBuffer.consume(event)
        liveTextDirty = true
        if event.type == "RUN_ERROR" { error = event.message ?? String(localized: "Task failed.") }
    }

    private func flushLiveText() {
        guard liveTextDirty else { return }
        if let parts = activityBuffer.drain() {
            liveParts = parts
            liveText = parts.filter { $0.type == "text" }.compactMap(\.text).joined(separator: "\n\n")
        }
        liveTextDirty = false
    }

    private func syncRunning(_ saved: Chat) {
        chats = chats.map { item in
            guard item.id == saved.id else { return item }
            var updated = item
            updated.isRunning = saved.isRunning
            return updated
        }
    }

    func watchApprovals(_ id: String) async {
        pendingApprovals = []; approvalChoices = [:]
        let current = generation
        var previousRunning = false
        var previousPending = false
        while !Task.isCancelled, selected?.id == id, generation == current {
            if foreground && !approvalBusy, let client {
                do {
                    let state = try await client.approvals(id)
                    guard !Task.isCancelled, selected?.id == id, generation == current else { return }
                    if !approvalBusy {
                        if state.pending != pendingApprovals { approvalChoices = [:] }
                        pendingApprovals = state.pending
                    }
                    if state.isRunning && !streaming { observe(id, client: client) }
                    if !state.isRunning && !streaming && liveParts.isEmpty && (previousRunning || previousPending && state.pending.isEmpty) {
                        let saved = try await client.chat(id)
                        guard !Task.isCancelled, selected?.id == id, generation == current else { return }
                        selected = saved; syncRunning(saved); liveText = ""; liveParts = []
                    }
                    previousRunning = state.isRunning; previousPending = !state.pending.isEmpty
                } catch {
                    if Task.isCancelled { return }
                    if case ClientError.http(let code) = error, [401, 403, 404].contains(code) {
                        pendingApprovals = []
                        if code != 404 { handle(error) }; return
                    }
                }
            }
            do { try await Task.sleep(for: .milliseconds(2500)) } catch { return }
        }
    }

    func chooseApproval(_ item: ApprovalRequest, action: ApprovalAction) async {
        guard let id = selected?.id, let client, !approvalBusy, device?.permissions.approveTools == true,
              pendingApprovals.contains(item), item.actions.contains(action) else { return }
        approvalChoices[item.id] = action.id
        guard pendingApprovals.allSatisfy({ approvalChoices[$0.id] != nil }) else { return }
        let pending = pendingApprovals
        let current = generation
        approvalBusy = true
        defer { if current == generation { approvalBusy = false; approvalChoices = [:] } }
        do {
            try await client.decideApprovals(id, pending: pending, choices: approvalChoices)
            guard current == generation, selected?.id == id else { return }
            pendingApprovals = []
            if pending.allSatisfy({ $0.kind == "tool" }) { observe(id, client: client) }
        } catch {
            if current == generation {
                handle(error)
                self.error = String(localized: "Approval could not be confirmed. Refresh before trying again.")
            }
        }
    }

    func stop() async {
        guard device?.permissions.stop == true, let id = selected?.id, let client else { return }
        do { try await client.stop(id) }
        catch { handle(error) }
    }

    func setForeground(_ active: Bool) async {
        foreground = active
        if !active {
            streamTask?.cancel()
            streaming = false
            liveText = ""; liveParts = []
            disconnectNode()
        } else {
            await refresh()
            if let chat = selected, chat.isRunning == true, let client {
                observe(chat.id, client: client)
            }
            if nodeEnabled { startNode() }
        }
    }

    func toggleNode(_ enabled: Bool) {
        nodeEnabled = enabled
        if enabled && foreground { startNode() } else { disconnectNode() }
    }

    private func disconnectNode() {
        nodeTask?.cancel()
        nodeTask = nil
        socket?.cancel(with: .goingAway, reason: nil)
        socket = nil
        nodeStatus = nodeEnabled ? String(localized: "Offline") : String(localized: "Off")
    }

    private func startNode() {
        disconnectNode()
        guard let client, let connection, foreground else { return }
        let ws = client.nodeSocket()
        socket = ws
        nodeStatus = String(localized: "Connecting")
        ws.resume()
        nodeTask = Task {
            do {
                try await sendNode(NodeProtocol.connect(name: "Suzent iPhone", platform: "ios", token: connection.nodeToken), to: ws)
                while !Task.isCancelled {
                    let message = try await ws.receive()
                    guard foreground, socket === ws else { return }
                    let data: Data
                    switch message {
                    case .string(let text): data = Data(text.utf8)
                    case .data(let bytes): data = bytes
                    @unknown default: continue
                    }
                    guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
                    switch value["type"] as? String {
                    case "pending": nodeStatus = String(localized: "Approve on desktop: \(value["pairing_code"] as? String ?? "")")
                    case "connected":
                        if let credential = value["device_token"] as? String, !credential.isEmpty {
                            var saved = connection
                            saved.nodeToken = credential
                            try CredentialStore.save(saved)
                            self.connection = saved
                        }
                        nodeStatus = String(localized: "Online · device.status")
                    case "error":
                        throw ClientError.invalidResponse
                    default:
                        if let reply = NodeProtocol.reply(to: value, platform: "ios") { try await sendNode(reply, to: ws) }
                    }
                }
            } catch {
                if !Task.isCancelled, socket === ws { nodeStatus = String(localized: "Disconnected — toggle to reconnect") }
                ws.cancel(with: .goingAway, reason: nil)
            }
        }
    }

    private func sendNode(_ value: [String: Any], to ws: URLSessionWebSocketTask) async throws {
        let data = try JSONSerialization.data(withJSONObject: value)
        try await ws.send(.string(String(decoding: data, as: UTF8.self)))
    }

    func forget() {
        pendingApprovals = []; approvalChoices = [:]; approvalBusy = false
        pairingTask?.cancel()
        do { try CredentialStore.clear() }
        catch { self.error = error.localizedDescription }
        generation = UUID()
        nodeEnabled = false
        disconnectNode()
        streamTask?.cancel()
        client?.close()
        client = nil
        connection = nil
        connected = false
        busy = false
        selected = nil
        chats = []
        canReconnect = false
        device = nil
        pairingInvitation = nil
        pairingCode = nil
        invitationText = ""
        origin = ""
        draft = ""
        streaming = false
        liveText = ""; liveParts = []
    }
}
