import Foundation
import SwiftUI
import SuzentCore

@MainActor @Observable final class MobileModel {
    var origin = ""
    var token = ""
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
                token = saved.hostToken
            }
        } catch { self.error = error.localizedDescription }
    }

    var needsHostToken: Bool {
        #if DEBUG && targetEnvironment(simulator)
        guard let backend = try? Backend(origin, allowHTTP: true) else { return true }
        return !["127.0.0.1", "::1", "[::1]", "localhost"].contains(backend.url.host ?? "")
        #else
        return true
        #endif
    }

    func connect() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        error = nil
        do {
            #if DEBUG
            let backend = try Backend(origin, allowHTTP: true)
            #else
            let backend = try Backend(origin)
            #endif
            let credential = token.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !needsHostToken || !credential.isEmpty else { throw ClientError.http(401) }
            let candidate = SuzentClient(backend: backend, token: credential)
            let listing: [Chat]
            do { listing = try await candidate.chats() }
            catch { candidate.close(); throw error }
            let saved = Connection(origin: backend.url.absoluteString, hostToken: credential,
                                   nodeToken: connection?.origin == backend.url.absoluteString ? connection?.nodeToken ?? "" : "")
            do { try CredentialStore.save(saved) }
            catch { candidate.close(); throw error }
            client?.close()
            client = candidate
            connection = saved
            chats = listing
            connected = true
            token = ""
        } catch { self.error = error.localizedDescription }
    }

    func refresh() async {
        guard let client else { return }
        let current = generation
        do {
            let listing = try await client.chats()
            guard generation == current else { return }
            chats = listing
            if let id = selected?.id, !streaming {
                let chat = try await client.chat(id)
                guard generation == current, selected?.id == id else { return }
                selected = chat
            }
        } catch { if generation == current { self.error = error.localizedDescription } }
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
        guard let client, !busy, !streaming else { return }
        busy = true
        defer { busy = false }
        do {
            let chat = try await client.createChat(title: String(localized: "Mobile conversation"))
            selected = chat
            await refresh()
        } catch { self.error = error.localizedDescription }
    }

    func send() async {
        guard let client, let id = selected?.id, !busy, !streaming else { return }
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
            self.error = String(localized: "Send could not be confirmed. Refresh history before sending again.")
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
                if !Task.isCancelled, generation == current { self.error = error.localizedDescription }
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
        guard let id = selected?.id, let client else { return }
        do { try await client.stop(id) }
        catch { self.error = error.localizedDescription }
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
        do { try CredentialStore.clear() }
        catch { self.error = error.localizedDescription; return }
        generation = UUID()
        nodeEnabled = false
        disconnectNode()
        streamTask?.cancel()
        client?.close()
        client = nil
        connection = nil
        connected = false
        selected = nil
        chats = []
        token = ""
        origin = ""
        draft = ""
        streaming = false
        liveText = ""
    }
}
