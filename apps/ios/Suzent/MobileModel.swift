import Foundation
import SwiftUI
import SuzentCore

@MainActor @Observable final class MobileModel {
    var origin = ""
    var invitationText = ""
    var pairingInvitation: PairingInvitation?
    var pairingCode: String?
    var device: ClientDevice?
    var canReconnect = false
    private var pairingTask: Task<Void, Never>?
    var chats: [Chat] = []
    var selected: Chat?
    var draft = ""
    var liveText = ""
    var error: String?
    var busy = false
    var streaming = false
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
        do {
            pairingInvitation = try PairingInvitation.parse(text, allowHTTP: allowsHTTP)
            invitationText = ""
            error = nil
        } catch { handle(error) }
    }

    func cancelPairing() {
        pairingTask?.cancel()
        pairingTask = nil
        pairingInvitation = nil
        pairingCode = nil
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
                let claim = try await bootstrap.claim(invitation, name: UIDevice.current.name)
                guard generation == current else { return }
                pairingCode = String(invitation.pairingId.prefix(6))
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
                        pairingInvitation = nil
                        try await activate(saved)
                        return
                    }
                    guard result.status == "pending" else { throw ClientError.invalidResponse }
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
        liveText = ""
        await refresh()
        if selected?.id == chat.id {
            observe(chat.id, client: client)
        }
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
            await refresh()
            if foreground { observe(id, client: client) }
        } catch {
            if case ClientError.http(401) = error { handle(error) }
            else { self.error = String(localized: "Send could not be confirmed. Refresh history before sending again.") }
        }
    }

    private func observe(_ id: String, client: SuzentClient) {
        guard !streaming, foreground else { return }
        streaming = true
        liveText = ""
        let current = generation
        streamTask = Task {
            do {
                try await client.observe(id) { [weak self] event in
                    await self?.receive(event, generation: current)
                }
                let saved = try await client.chat(id)
                guard generation == current, !Task.isCancelled, selected?.id == id else { return }
                selected = saved
                liveText = ""
            } catch {
                if !Task.isCancelled, generation == current { handle(error) }
            }
            guard generation == current, !Task.isCancelled else { return }
            streaming = false
        }
    }

    private func receive(_ event: StreamEvent, generation current: UUID) {
        guard generation == current, foreground else { return }
        if event.type == "STREAM_RESET" { liveText = "" }
        if event.type == "TEXT_MESSAGE_CONTENT" { liveText += event.delta ?? "" }
        if event.type == "RUN_ERROR" { error = event.message ?? String(localized: "Task failed.") }
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
            liveText = ""
            disconnectNode()
        } else {
            await refresh()
            if let chat = selected, let client {
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
        liveText = ""
    }
}
