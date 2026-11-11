import Foundation
import SwiftUI
import SuzentCore

@MainActor @Observable final class MobileModel {
    var origin = ""
    var invitationText = ""
    var pairingInvitation: PairingInvitation?
    var pairingPreview: PairingPreview?
    var pairingStatus: String?
    var awaitingDesktop = false
    var device: ClientDevice?
    var canReconnect = false
    var reconnecting = false
    var reconnectStage = 0
    var reconnectStatus: String?
    @ObservationIgnored private var reconnectTask: Task<Void, Never>?
    private var pairingTask: Task<Void, Never>?
    var chatPages: [ChatPageQuery: ChatPage] = [:]
    var loadingPages: Set<ChatPageQuery> = []
    private var navigationRevision = UUID()
    var navigationVersion = 0
    private var lastNavigationRefresh = Date.distantPast

    func pageChats(_ query: ChatPageQuery) -> [Chat] {
        let byID = Dictionary(chats.map { ($0.id, $0) }, uniquingKeysWith: { _, new in new })
        return (chatPages[query]?.chats ?? []).compactMap { byID[$0.id] }
    }

    func loadPage(_ query: ChatPageQuery, more: Bool = false) async {
        guard let client, !loadingPages.contains(query) else { return }
        if !more && chatPages[query] != nil { return }
        let offset = more ? chatPages[query]?.nextOffset : 0
        guard let offset else { return }
        let current = generation
        let revision = navigationRevision
        loadingPages.insert(query)
        defer { if revision == navigationRevision { loadingPages.remove(query) } }
        do {
            let page = try await client.chatPage(query, offset: offset, limit: 30)
            guard current == generation, revision == navigationRevision, !Task.isCancelled else { return }
            if query.kind == "search" {
                chatPages = chatPages.filter { $0.key.kind != "search" || $0.key == query }
            }
            chatPages[query] = more ? chatPages[query]?.appending(page) ?? page : page
            mergeNavigationChats(page.chats)
            let retained = Set(chatPages.values.flatMap { $0.chats.map(\.id) })
            chats.removeAll { !$0.isRegent && $0.id != selected?.id && !retained.contains($0.id) }
        } catch is CancellationError { }
        catch { if current == generation && revision == navigationRevision { handle(error) } }
    }

    private func mergeNavigationChats(_ updates: [Chat]) {
        let ids = Set(updates.map(\.id))
        chats = chats.filter { !ids.contains($0.id) } + updates
    }

    private func applyNavigation(_ initial: InitialNavigation) {
        navigationRevision = UUID()
        navigationVersion += 1
        loadingPages = []
        chatPages = [ChatPageQuery(): initial.recent, ChatPageQuery("pinned"): initial.pinned]
        chats = initial.chats
        projects = initial.metadata.projects
        lastNavigationRefresh = Date()
    }

    private func refreshNavigation(_ client: any MobileClient, poll: Bool) async throws {
        let current = generation
        let revision = navigationRevision
        if !poll || chatPages.isEmpty {
            let initial = try await client.initialNavigation()
            guard current == generation, revision == navigationRevision else { return }
            applyNavigation(initial)
        } else {
            let requested = Set(chats.map(\.id))
            let updates = try await client.chatStatuses(Array(requested))
            guard current == generation, revision == navigationRevision else { return }
            chats = chats.filter { !requested.contains($0.id) } + updates
            if Date().timeIntervalSince(lastNavigationRefresh) >= 60 {
                let recentIDs = chatPages[ChatPageQuery()]?.chats.map(\.id)
                let pinnedIDs = chatPages[ChatPageQuery("pinned")]?.chats.map(\.id)
                let metadata = try await client.navigationMetadata()
                let recent = chatPages[ChatPageQuery()].map { $0.chats.count <= 30 } == true
                    ? try await client.chatPage(ChatPageQuery(), offset: 0, limit: 30) : nil
                let pinned = (chatPages[ChatPageQuery("pinned")]?.chats.count ?? 0) <= 30
                    ? try await client.chatPage(ChatPageQuery("pinned"), offset: 0, limit: 30) : nil
                guard current == generation, revision == navigationRevision else { return }
                projects = metadata.projects
                if let regent = metadata.regent { mergeNavigationChats([regent]) }
                if let recent, !loadingPages.contains(ChatPageQuery()), chatPages[ChatPageQuery()]?.chats.map(\.id) == recentIDs {
                    chatPages[ChatPageQuery()] = recent; mergeNavigationChats(recent.chats)
                }
                if let pinned, !loadingPages.contains(ChatPageQuery("pinned")), chatPages[ChatPageQuery("pinned")]?.chats.map(\.id) == pinnedIDs {
                    chatPages[ChatPageQuery("pinned")] = pinned; mergeNavigationChats(pinned.chats)
                }
                lastNavigationRefresh = Date()
            }
        }
    }

    var chats: [Chat] = []
    var projects: [Project] = []
    var scheduledTasks: [ScheduledTask] = []
    var selectedModel: String?
    var sentVersion = 0
    var openedVersion = 0
    private(set) var openingChatID: String?
    var pinnedVersion = 0
    var pairingVersion = 0
    @ObservationIgnored private var drafts: [String: String] = [:]
    var selected: Chat?
    var draft = ""
    var attachments: [PendingAttachment] = []
    var attachmentsSupported = false
    var voiceSupported = false
    var overviewSupported = false
    var surfacesSupported = false
    var steerSupported = false
    private(set) var queues = MessageQueues()
    let voice = VoiceSession()

    var voiceUnavailableReason: String? {
        if isDemo { return String(localized: "Voice is unavailable in the offline demo. Connect to your desktop to talk with Suzent.") }
        if !voiceSupported { return String(localized: "Update and restart your desktop, then configure a realtime model in Settings → Voice & audio.") }
        if device?.permissions.send != true || device?.permissions.stop != true {
            return String(localized: "Enable Send messages and Stop responses for this phone in desktop Settings → Devices.")
        }
        if selected?.id.isEmpty == true && device?.permissions.createChats != true {
            return String(localized: "Enable Create conversations for this phone, or open an existing conversation.")
        }
        return nil
    }

    /// The plan and context panel reads on demand; nil while unavailable.
    func overview(_ chatID: String) async -> ChatOverview? {
        guard overviewSupported, !chatID.isEmpty, let client else { return nil }
        return try? await client.overview(chatID)
    }

    func startVoice() {
        if let reason = voiceUnavailableReason { error = reason; return }
        guard voiceSupported, !busy, !streaming, device?.permissions.send == true,
              device?.permissions.stop == true, let client = client as? SuzentClient,
              let chat = selected else { return }
        let current = generation
        error = nil
        voice.onError = { [weak self] message in self?.error = message }
        voice.onRefresh = { [weak self] in Task { await self?.refresh() } }
        voice.start { [weak self] in
            guard let self, self.generation == current else { throw CancellationError() }
            var id = chat.id
            if id.isEmpty {
                guard self.device?.permissions.createChats == true else { throw CancellationError() }
                self.busy = true
                defer { self.busy = false }
                let created = try await client.createChat(title: String(localized: "Voice conversation"), projectID: chat.projectId)
                try Task.checkCancellation()
                guard self.generation == current else { throw CancellationError() }
                self.selected = created
                self.chats.insert(created, at: 0)
                id = created.id
            }
            return try client.voiceSocket(chatID: id)
        }
    }
    var liveParts: [MessagePart] = []
    var regentVisible = false
    var pendingApprovals: [ApprovalRequest] = []
    var approvalChoices: [String: String] = [:]
    var approvalBusy = false
    var error: String?
    var busy = false
    /// Loading the demo keeps the welcome screen up instead of the pairing progress view.
    private(set) var startingDemo = false
    var streaming = false
    var stopInFlight = false
    var isDemo = false
    var demoPrompts: [String] = []
    var connected = false
    var nodeEnabled = false
    var nodeStatus = String(localized: "Off")
    private var store = SavedDesktops()
    var desktops: [SavedDesktop] { store.desktops }
    var activeDesktopId: String? { store.activeId }
    var activeDesktop: SavedDesktop? { store.active }
    /// The desktop a switch is probing; the current session stays usable until it succeeds.
    var checkingDesktopId: String?
    private var repairActive = false
    private var connection: Connection? { store.active?.connection }
    private var client: (any MobileClient)?
    private let connectionUpgrade = ConnectionUpgrade<SuzentClient>()
    // Previously captured clients may still serve polling requests or the device socket.
    private var retiredClients: [SuzentClient] = []
    private var streamTask: Task<Void, Never>?
    private var nodeTask: Task<Void, Never>?
    private var socket: (any MobileSocket)?
    /// None of the invitation's origins answered, so pairing goes through the desktop's relay.
    private var pairingViaRelay = false
    private var generation = UUID()
    private var foreground = true

    init() {
        AttachmentStaging.clear()
        do {
            try CredentialStore.clearIfFromPreviousInstall()
            store = try CredentialStore.load()
            if store.active == nil { store.activeId = store.desktops.first?.id }
            if let saved = connection {
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

    func startDemo() async {
        guard !busy, !streaming else { return }
        busy = true
        startingDemo = true
        defer { busy = false; startingDemo = false }
        do {
            let directory = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                       appropriateFor: nil, create: true)
            let demo = try DemoClient(storageURL: directory.appendingPathComponent("OfflineDemo/workspace.json"))
            let session = try await demo.clientSession()
            let navigation = try await demo.initialNavigation()
            let taskList = try await demo.scheduledTasks()
            let composer = try await demo.composer()
            clearSession()
            error = nil
            client = demo
            isDemo = true
            demoPrompts = demo.prompts
            origin = "demo://offline"
            canReconnect = false
            device = session.device
            attachmentsSupported = true
            overviewSupported = true
            surfacesSupported = true
            steerSupported = true
            applyNavigation(navigation); scheduledTasks = taskList
            selected = composer
            connected = true
            openedVersion += 1
        } catch { self.error = error.localizedDescription }
    }

    func resetDemo() async {
        guard let demo = client as? DemoClient, !busy else { return }
        generation = UUID()
        streamTask?.cancel(); streaming = false; liveParts = []
        pendingApprovals = []; approvalChoices = [:]; approvalBusy = false; drafts = [:]; draft = ""; error = nil
        discardAttachments(); discardQueues()
        do {
            try demo.reset()
            selected = try await demo.composer()
            selectedModel = nil
            await refresh()
            openedVersion += 1
        } catch { self.error = error.localizedDescription }
    }

    func exitDemo() {
        guard isDemo, !busy else { return }
        clearSession()
        isDemo = false; demoPrompts = []; error = nil
    }

    func stageInvitation(_ text: String) {
        guard !busy else { return }
        let invitation: PairingInvitation
        do { invitation = try PairingInvitation.parse(text, allowHTTP: allowsHTTP) }
        catch { handle(error); return }
        invitationText = ""
        pairingInvitation = nil
        pairingPreview = nil
        pairingViaRelay = false
        error = nil
        busy = true
        let current = generation
        let allowHTTP = allowsHTTP
        pairingStatus = String(localized: "QR code recognized. Connecting to your desktop…")
        pairingTask = Task {
            defer { if generation == current { busy = false; pairingStatus = nil } }
            do {
                let selected: (invitation: PairingInvitation, value: (DeviceTrust?, PairingPreview?))
                var viaRelay = false
                do {
                    selected = try await invitation.resolving { origin -> (DeviceTrust?, PairingPreview?) in
                        var trust = invitation.tls
                        if trust == nil, let fingerprint = invitation.tlsFingerprint {
                            trust = try await DeviceTrust.fetch(origin: origin, fingerprint: fingerprint)
                        }
                        let probe = try SuzentClient(backend: try Backend(origin, allowHTTP: allowHTTP), token: "", probeOnly: true, deviceTrust: trust)
                        defer { probe.close() }
                        _ = try await probe.capabilities()
                        return (trust, invitation.phoneConfirmation ? try await probe.pairingPreview(invitation) : nil)
                    }
                } catch let direct {
                    guard let relay = invitation.relay else { throw direct }
                    try Task.checkCancellation()
                    do {
                        let probe = try SuzentClient(relay: relay, token: "", probeOnly: true)
                        defer { probe.close() }
                        _ = try await probe.capabilities()
                        selected = (invitation, (invitation.tls, invitation.phoneConfirmation ? try await probe.pairingPreview(invitation) : nil))
                        viaRelay = true
                    } catch {
                        try Task.checkCancellation()
                        throw direct
                    }
                }
                guard generation == current, !Task.isCancelled else { return }
                pairingViaRelay = viaRelay
                pairingPreview = selected.value.1
                var resolved = selected.invitation
                resolved.tls = selected.value.0
                pairingInvitation = resolved
            } catch { if generation == current, !Task.isCancelled { handle(error) } }
        }
    }

    func cancelPairing() {
        pairingTask?.cancel()
        pairingTask = nil
        pairingStatus = nil
        pairingInvitation = nil
        awaitingDesktop = false
        pairingPreview = nil
        busy = false
        generation = UUID()
    }

    /// Repairing the active desktop reuses its credential; otherwise a saved desktop matching the invitation is the target.
    func beginPairing(repairActive: Bool) {
        self.repairActive = repairActive
        error = nil
    }

    func approveDestination() {
        guard let invitation = pairingInvitation, !busy else { return }
        busy = true
        error = nil
        let current = generation
        let target = repairActive ? store.active : store.matching(invitation)
        let existing = target?.connection
        let previewName = pairingPreview?.desktopName
        let viaRelay = pairingViaRelay
        pairingTask = Task {
            var savedID = target?.id
            defer { if generation == current { busy = false; awaitingDesktop = false; pairingStatus = nil } }
            pairingStatus = String(localized: "Sending connection request…")
            do {
                let backend = try Backend(invitation.origin, allowHTTP: allowsHTTP)
                let bootstrap: SuzentClient
                if viaRelay, let relay = invitation.relay {
                    bootstrap = try SuzentClient(relay: relay, token: "")
                } else {
                    bootstrap = try SuzentClient(backend: backend, token: "", deviceTrust: invitation.tls)
                }
                defer { bootstrap.close() }
                let capabilities = try await bootstrap.capabilities()
                let previous = capabilities.pairingRepair == 1 ? existing?.hostToken : nil
                try Task.checkCancellation()
                let claim = try await bootstrap.claim(invitation, name: UIDevice.current.name,
                                                      confirmPermissions: invitation.phoneConfirmation && pairingPreview != nil,
                                                      repairProof: previous.map { pairingRepairProof(token: $0, invitation: invitation, side: "phone") },
                                                      rotate: existing?.origin != backend.url.absoluteString,
                                                      installationID: capabilities.installationId == 1 ? try? CredentialStore.installationID() : nil)
                let recognized = previous.map { claim.serverProof == pairingRepairProof(token: $0, invitation: invitation, side: "desktop") } ?? false
                if claim.serverProof != nil && !recognized { throw ClientError.invalidResponse }
                guard generation == current else { return }
                if !invitation.phoneConfirmation { awaitingDesktop = true }
                pairingStatus = String(localized: "Finishing connection…")
                while Date().timeIntervalSince1970 < claim.expiresAt {
                    try Task.checkCancellation()
                    let result = try await bootstrap.collect(pairingID: invitation.pairingId, pickupSecret: claim.pickupSecret)
                    guard generation == current else { return }
                    if result.status == "denied" { throw PairingError.denied }
                    if result.status == "approved" {
                        if result.reused == true && (!recognized || existing?.origin != backend.url.absoluteString) { throw ClientError.invalidResponse }
                        guard let token = result.reused == true ? previous : result.token, !token.isEmpty, result.device != nil else {
                            throw ClientError.invalidResponse
                        }
                        let saved = Connection(origins: invitation.origins, tls: invitation.tls, previousOrigins: existing?.origins, previousTLS: existing?.tls, origin: backend.url.absoluteString, hostToken: token, nodeToken: recognized ? existing?.nodeToken ?? "" : "", clientProtocol: 1,
                                               previousToken: recognized && result.reused != true ? previous : nil,
                                               previousOrigin: recognized && result.reused != true ? existing?.origin : nil,
                                               relay: invitation.relay)
                        let id = target?.id ?? UUID().uuidString
                        var next = store
                        next.upsert(SavedDesktop(id: id, name: previewName ?? target?.name ?? saved.host, connection: saved))
                        // Without a live session there is nothing to keep, so the new credential becomes the reconnect target at once.
                        if !connected || next.activeId == nil { next.activeId = id }
                        try CredentialStore.save(next)
                        store = next
                        savedID = id
                        if store.activeId == id { origin = saved.origin; canReconnect = true }
                        try await activate(id, saved)
                        repairActive = false
                        busy = false; awaitingDesktop = false; pairingStatus = nil
                        pairingVersion += 1
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
                    if case ClientError.http(401) = error { revoke(savedID) } else { handle(error) }
                }
            }
        }
    }

    /// Builds the session on a separate client and swaps it in only once everything has loaded,
    /// so a failed switch leaves the current desktop untouched.
    private func activate(_ id: String, _ stored: Connection) async throws {
        connectionUpgrade.cancel()
        var saved = stored
        var throughRelay: RelayRoute?
        reconnectStage = 0
        reconnectStatus = String(localized: "Finding a connection")
        let trust = saved.tls
        let relay = saved.relay
        let allowHTTP = allowsHTTP
        let route = try await resolveConnectionRoute(
            origins: [saved.origin] + (saved.origins ?? []), hasRelay: relay != nil
        ) { route in
            let probe: SuzentClient
            switch route {
            case .direct(let origin):
                probe = try SuzentClient(backend: try Backend(origin, allowHTTP: allowHTTP), token: "", probeOnly: true, deviceTrust: trust)
            case .relay:
                guard let relay else { throw PairingError.unreachable }
                probe = try SuzentClient(relay: relay, token: "", probeOnly: true)
            }
            defer { probe.close() }
            _ = try await probe.capabilities()
        }
        switch route {
        case .direct(let origin): saved.origin = origin
        case .relay: throughRelay = relay
        }
        guard saved.clientProtocol == 1 else { throw PairingError.incompatible }
        reconnectStage = 2
        reconnectStatus = String(localized: "Verifying connection")
        let candidate: SuzentClient
        if let throughRelay {
            candidate = try SuzentClient(relay: throughRelay, token: saved.hostToken)
        } else {
            candidate = try SuzentClient(backend: try Backend(saved.origin, allowHTTP: allowsHTTP), token: saved.hostToken, deviceTrust: saved.tls)
        }
        do {
            if let previous = saved.previousToken {
                var restored = saved
                do { try await candidate.confirmPairing() }
                catch ClientError.http(401) {
                    try Task.checkCancellation()
                    restored = Connection(origins: saved.previousOrigins, tls: saved.previousTLS, origin: saved.previousOrigin ?? saved.origin, hostToken: previous, nodeToken: saved.nodeToken, clientProtocol: 1, relay: saved.relay)
                    try storeConnection(id, restored)
                    if store.activeId == id { origin = restored.origin }
                    candidate.close(); try await activate(id, restored); return
                }
                restored.previousToken = nil
                restored.previousOrigin = nil
                restored.previousTLS = nil
                restored.previousOrigins = nil
                try Task.checkCancellation()
                try storeConnection(id, restored)
                saved = restored
            } else {
                // A grant replacing a forgotten one stays provisional until confirmed, so activation
                // must not succeed without it. Confirming a finalized grant is a no-op.
                try await candidate.confirmPairing()
            }
            _ = try await candidate.capabilities()
            let session = try await candidate.clientSession()
            reconnectStage = 3
            reconnectStatus = String(localized: "Syncing desktop")
            let navigation = try await candidate.initialNavigation()
            let taskList = session.supportsScheduledTasks ? try await candidate.scheduledTasks() : []
            let initialChat = try await candidate.composer()
            try Task.checkCancellation()
            guard store.desktop(id) != nil else { throw CancellationError() }
            saved.relay = session.relay?.validated(allowHTTP: allowsHTTP)
            var next = store
            next.update(id, connection: saved)
            if let name = session.desktopName { next.rename(id, to: name) }
            let switching = next.activeId != id
            next.activeId = id
            try CredentialStore.save(next)
            if switching { resetSessionState() }
            store = next
            origin = saved.origin
            canReconnect = true
            retiredClients.forEach { $0.close() }
            retiredClients = []
            client?.close()
            client = candidate
            device = session.device
            attachmentsSupported = session.supportsAttachments
            voiceSupported = session.voice == 1
            overviewSupported = session.supportsChatOverview
            surfacesSupported = session.supportsSurfaces
            steerSupported = session.supportsSteer
            applyNavigation(navigation)
            scheduledTasks = taskList
            selected = initialChat
            restoreModel(initialChat)
            connected = true
            if throughRelay != nil { startDirectUpgrade(id, saved, candidate) }
        } catch { candidate.close(); throw error }
    }

    private func startDirectUpgrade(_ id: String, _ saved: Connection, _ relayed: SuzentClient) {
        let allowHTTP = allowsHTTP
        let deviceID = device?.deviceId
        connectionUpgrade.start(
            prepare: {
                let route = try await resolveConnectionRoute(origins: [saved.origin] + (saved.origins ?? []), hasRelay: false) { route in
                    guard case .direct(let origin) = route else { throw PairingError.unreachable }
                    let probe = try SuzentClient(backend: try Backend(origin, allowHTTP: allowHTTP), token: "", probeOnly: true, deviceTrust: saved.tls)
                    defer { probe.close() }
                    _ = try await probe.capabilities()
                }
                guard case .direct(let origin) = route else { throw PairingError.unreachable }
                let direct = try SuzentClient(backend: try Backend(origin, allowHTTP: allowHTTP), token: saved.hostToken, deviceTrust: saved.tls)
                do {
                    try await withConnectionTimeout(.seconds(5)) {
                        _ = try await direct.capabilities()
                        let session = try await direct.clientSession()
                        guard session.device.deviceId == deviceID else { throw ClientError.invalidResponse }
                    }
                    return direct
                } catch { direct.close(); throw error }
            },
            isCurrent: { [weak self] in
                guard let self else { return false }
                return foreground && connected && !isDemo && store.activeId == id &&
                    (client as? SuzentClient) === relayed && connection?.hostToken == saved.hostToken
            },
            isIdle: { [weak self] in
                guard let self else { return false }
                return !busy && !streaming && !voice.active && !approvalBusy && !stopInFlight && checkingDesktopId == nil
            },
            validate: { direct in
                try await withConnectionTimeout(.seconds(5)) {
                    let session = try await direct.clientSession()
                    guard session.device.deviceId == deviceID else { throw ClientError.invalidResponse }
                }
            },
            install: { [weak self] direct in
                guard let self, var latest = store.desktop(id)?.connection else { throw CancellationError() }
                latest.origin = direct.backend.url.absoluteString
                try storeConnection(id, latest)
                origin = latest.origin
                retiredClients.append(relayed)
                client = direct
            },
            discard: { $0.close() }
        )
    }

    private func storeConnection(_ id: String, _ connection: Connection) throws {
        var next = store
        next.update(id, connection: connection)
        try CredentialStore.save(next)
        store = next
    }

    func connect(keepingError: Bool = false) async {
        guard !isDemo else { return }
        guard let id = store.activeId, let connection, canReconnect, !busy else { return }
        busy = true
        reconnecting = true
        if !keepingError { error = nil }
        let attempt = Task {
            do {
                try await withConnectionTimeout { try await self.activate(id, connection) }
            } catch {
                guard !Task.isCancelled else { return }
                if let network = error as? URLError, [.timedOut, .notConnectedToInternet, .cannotConnectToHost, .cannotFindHost, .networkConnectionLost].contains(network.code) {
                    self.error = String(localized: "Could not reach your desktop. Check Wi-Fi or Tailscale and make sure Suzent is running, then retry or pair again.")
                } else { handle(error) }
            }
        }
        reconnectTask = attempt
        await withTaskCancellationHandler {
            await attempt.value
        } onCancel: { attempt.cancel() }
        releaseReconnect(attempt)
    }

    /// A switch to another desktop may have cancelled this attempt and taken over; the newer attempt keeps the busy state.
    private func releaseReconnect(_ attempt: Task<Void, Never>) {
        guard reconnectTask == attempt else { return }
        busy = false; reconnecting = false; reconnectStatus = nil; reconnectStage = 0; reconnectTask = nil
    }

    /// Probes the target with the reconnect timeouts and keeps the current desktop if it cannot be reached.
    func switchDesktop(_ id: String) async {
        guard !isDemo, let target = store.desktop(id) else { return }
        if connected && id == store.activeId { return }
        let idle = !connected
        if idle, reconnecting, let pending = reconnectTask {
            guard checkingDesktopId != id else { return }
            // Nothing open to protect: abandon the attempt in progress and try this desktop instead.
            pending.cancel()
            await pending.value
            // A later tap may already have taken over while this one waited.
            guard !connected, reconnectTask == nil || reconnectTask == pending else { return }
        } else {
            guard checkingDesktopId == nil, !busy else { return }
        }
        checkingDesktopId = id
        if idle { busy = true; reconnecting = true }
        error = nil
        let attempt = Task {
            do {
                try await withConnectionTimeout { try await self.activate(id, target.connection) }
            } catch {
                guard !Task.isCancelled else { return }
                if case ClientError.http(401) = error {
                    forgetDesktop(id, reconnectNext: false)
                    self.error = String(localized: "Access to \(target.name) was revoked or expired. Pair it again.")
                } else { self.error = String(localized: "Couldn't reach \(target.name)") }
            }
        }
        reconnectTask = attempt
        await withTaskCancellationHandler {
            await attempt.value
        } onCancel: { attempt.cancel() }
        guard reconnectTask == attempt else {
            if checkingDesktopId == id { checkingDesktopId = nil }
            return
        }
        checkingDesktopId = nil
        if idle { releaseReconnect(attempt) } else { reconnectTask = nil }
    }

    func cancelReconnect() { reconnectTask?.cancel() }

    private func handle(_ failure: Error) {
        if case ClientError.http(401) = failure { revoke(store.activeId) }
        else { error = failure.localizedDescription }
    }

    private func revoke(_ id: String?) {
        if isDemo { exitDemo() } else if let id { forgetDesktop(id) }
        error = String(localized: "Access was revoked or expired. Pair this phone again.")
    }

    func watchNavigation() async {
        while !Task.isCancelled && connected {
            if foreground && !busy {
                await refresh(poll: true)
            }
            do { try await Task.sleep(for: .seconds(10)) } catch { return }
        }
    }

    func refresh(poll: Bool = false) async {
        guard let client else { return }
        let current = generation
        do {
            let session = try await client.clientSession()
            let scopeChanged = device?.permissions.allChats != session.device.permissions.allChats || device?.permissions.chatIds != session.device.permissions.chatIds
            try await refreshNavigation(client, poll: poll && !scopeChanged)
            let taskList = session.supportsScheduledTasks ? try await client.scheduledTasks() : []
            guard generation == current else { return }
            device = session.device
            attachmentsSupported = session.supportsAttachments
            voiceSupported = session.voice == 1
            overviewSupported = session.supportsChatOverview
            surfacesSupported = session.supportsSurfaces
            steerSupported = session.supportsSteer
            scheduledTasks = taskList
            if !isDemo, let id = store.activeId, let name = session.desktopName, store.active?.name != name {
                var next = store
                next.rename(id, to: name)
                if (try? CredentialStore.save(next)) != nil { store = next }
            }
            if let id = selected?.id, !id.isEmpty, !streaming {
                let chat = try await client.chat(id)
                guard generation == current, selected?.id == id, !streaming else { return }
                selected = chat
                if chat.isRegent {
                    if regentVisible && (chat.regent?.unread ?? 0) > 0 { try await client.markRead(id) }
                    if current == generation && selected?.id == id && chat.isRunning == true && liveParts.isEmpty { observe(id, client: client) }
                }
            }
        } catch { if generation == current { handle(error) } }
    }

    func manageChat(_ chat: Chat, action: String, value: String? = nil) async {
        guard let client, !busy, device?.permissions.manageChats == true else { return }
        busy = true
        defer { busy = false }
        let current = generation
        do {
            try await client.manageChat(chat.id, action: action, value: value)
            guard generation == current else { return }
            if action == "delete" {
                drafts.removeValue(forKey: chat.id)
                queues.of(chat.id).flatMap(\.attachments).forEach { try? FileManager.default.removeItem(at: $0.url) }
                queues.clear(chat.id)
                chats.removeAll { $0.id == chat.id }
                if selected?.id == chat.id {
                    streamTask?.cancel()
                    selected = nil
                    streaming = false
                    liveParts = []; pendingApprovals = []; draft = ""; discardAttachments()
                }
            }
            try await refreshNavigation(client, poll: false)
            guard generation == current else { return }
            let listing = chats
            if action == "pin", listing.contains(where: { $0.id == chat.id && $0.pinned == true }) { pinnedVersion += 1 }
            if let updated = listing.first(where: { $0.id == selected?.id }) {
                selected?.title = updated.title
                selected?.projectId = updated.projectId
                selected?.projectName = updated.projectName
                selected?.pinned = updated.pinned
            }
        } catch { if generation == current { handle(error) } }
    }

    func open(_ chat: Chat) async {
        guard let client, !busy else { return }
        voice.stop()
        if let id = selected?.id { drafts[id] = draft }
        generation = UUID()
        streamTask?.cancel()
        streaming = false
        pendingApprovals = []
        if chat.id != selected?.id { discardAttachments() }
        if selected?.id != chat.id { selected = chat }
        openingChatID = chat.id
        selectedModel = UserDefaults.standard.string(forKey: "suzent.chatModel.\(origin).\(chat.id)")
        draft = drafts[chat.id] ?? ""
        liveParts = []
        let current = generation
        defer { if current == generation { openingChatID = nil } }
        do {
            let saved = try await client.chat(chat.id)
            guard current == generation, selected?.id == chat.id else { return }
            selected = saved
            if saved.isRegent { try await client.markRead(saved.id) }
            guard current == generation, selected?.id == saved.id else { return }
            restoreModel(saved)
            openedVersion += 1
            syncRunning(saved)
            if saved.isRunning == true { observe(chat.id, client: client) }
        } catch { if current == generation { handle(error) } }
    }

    func messageAction(_ message: DisplayMessage, action: String, text: String? = nil) async {
        guard let client, let id = selected?.id, !id.isEmpty, !busy, !streaming else { return }
        busy = true
        defer { busy = false }
        do {
            let target = try await client.messageAction(id, index: message.messageIndex, action: action, text: text, model: selectedModel)
            let chat = try await client.chat(target)
            busy = false
            await open(chat)
            await refresh()
        } catch { handle(error) }
    }

    func selectModel(_ model: String?) {
        selectedModel = model
        UserDefaults.standard.set(model, forKey: "suzent.lastModel.\(origin)")
        if let id = selected?.id, !id.isEmpty {
            UserDefaults.standard.set(model, forKey: "suzent.chatModel.\(origin).\(id)")
        }
    }

    private func restoreModel(_ chat: Chat) {
        let key = chat.id.isEmpty ? "suzent.lastModel.\(origin)" : "suzent.chatModel.\(origin).\(chat.id)"
        let remembered = UserDefaults.standard.string(forKey: key)
        selectedModel = remembered.flatMap { (chat.models ?? []).contains($0) ? $0 : nil }
        // Once the backend acknowledges a pending choice, let future desktop changes win.
        if !chat.id.isEmpty, remembered == chat.model || selectedModel == nil {
            UserDefaults.standard.removeObject(forKey: key)
            selectedModel = nil
        }
    }

    func createChat(projectID: String? = nil) async {
        guard let client, device?.permissions.createChats == true, !busy else { return }
        voice.stop()
        let current = generation
        busy = true
        defer { busy = false }
        do {
            if let id = selected?.id { drafts[id] = draft }
            var chat = try await client.composer()
            guard generation == current else { return }
            if let projectID {
                chat.projectId = projectID
                chat.projectName = projects.first { $0.id == projectID }?.name
            }
            generation = UUID()
            streamTask?.cancel()
            streamTask = nil
            streaming = false
            pendingApprovals = []; approvalChoices = [:]
            liveParts = []
            selected = chat
            restoreModel(chat)
            draft = ""
            discardAttachments()
        } catch { handle(error) }
    }

    func stage(_ load: @escaping @Sendable () async throws -> [PendingAttachment]) async {
        guard !busy else { return }
        do {
            let staged = try await load()
            let room = max(0, maxAttachments - attachments.count)
            attachments += staged.prefix(room)
            staged.dropFirst(room).forEach { try? FileManager.default.removeItem(at: $0.url) }
            if staged.count > room { error = String(localized: "You can attach up to \(maxAttachments) items per message.") }
        } catch {
            self.error = String(localized: "That item could not be read. Try attaching it again.")
        }
    }

    func removeAttachment(_ attachment: PendingAttachment) {
        attachments.removeAll { $0.id == attachment.id }
        try? FileManager.default.removeItem(at: attachment.url)
    }

    private func discardAttachments() {
        attachments.forEach { try? FileManager.default.removeItem(at: $0.url) }
        attachments = []
    }

    private func discardQueues() {
        queues.attachments.forEach { try? FileManager.default.removeItem(at: $0.url) }
        queues = MessageQueues()
    }

    func send() async {
        _ = await submit(draft.trimmingCharacters(in: .whitespacesAndNewlines), outgoing: attachments, fromDraft: true)
    }

    var queued: [QueuedMessage] { queues.of(selected?.id) }
    /// Whether typed text can redirect the running turn here, rather than only wait in the queue.
    var redirectSupported: Bool { steerSupported && device?.permissions.stop == true }

    /// Holds the composer's message until this conversation's running turn ends.
    func queue() {
        guard let id = selected?.id, !id.isEmpty, !busy, device?.permissions.send == true else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty || !attachments.isEmpty else { return }
        queues.add(QueuedMessage(text: text, attachments: attachments), to: id)
        attachments = []
        draft = ""; drafts[id] = nil
    }

    func removeQueued(_ item: QueuedMessage) {
        guard let id = selected?.id else { return }
        item.attachments.forEach { try? FileManager.default.removeItem(at: $0.url) }
        queues.remove(item.id, from: id)
    }

    func clearQueued() {
        guard let id = selected?.id else { return }
        queued.flatMap(\.attachments).forEach { try? FileManager.default.removeItem(at: $0.url) }
        queues.clear(id)
    }

    /// Redirects the running turn with the composer's text, like Enter mid-turn on desktop; attachments stay put.
    func redirect() async {
        _ = await steer(draft.trimmingCharacters(in: .whitespacesAndNewlines), fromDraft: true)
    }

    /// Pulls one message out of line and redirects with it now; its attachments go back to the composer.
    func redirectQueued(_ item: QueuedMessage) async {
        guard let id = selected?.id, !busy, !item.text.isEmpty, queued.contains(item) else { return }
        queues.remove(item.id, from: id)
        if !item.attachments.isEmpty { attachments = Array((item.attachments + attachments).prefix(maxAttachments)) }
        if !(await steer(item.text, fromDraft: false)) { restore(QueuedMessage(text: item.text)) }
    }

    /// Sends the next queued message once this conversation is idle; called whenever that may have changed.
    func releaseQueued() async {
        guard let chat = selected, let next = queues.of(chat.id).first else { return }
        guard !busy, !streaming, chat.isRunning != true, pendingApprovals.isEmpty, !approvalBusy, foreground else { return }
        queues.remove(next.id, from: chat.id)
        if !(await submit(next.text, outgoing: next.attachments, fromDraft: false)) { restore(next) }
    }

    // A message that could not go out returns to the composer, never back into the queue, so a failing
    // desktop is not retried in a loop and nothing typed is lost.
    private func restore(_ item: QueuedMessage) {
        draft = [item.text, draft].filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.joined(separator: "\n\n")
        attachments = Array((item.attachments + attachments).prefix(maxAttachments))
    }

    private func steer(_ text: String, fromDraft: Bool) async -> Bool {
        guard let client, redirectSupported, device?.permissions.send == true, let id = selected?.id, !id.isEmpty,
              !busy, !text.isEmpty else { return false }
        busy = true
        error = nil
        defer { busy = false }
        let current = generation
        do {
            try await client.steer(text, chatID: id, model: selectedModel)
            guard generation == current else { return true }
            if fromDraft { draft = ""; drafts[id] = nil }
            sentVersion += 1
            // The interrupted turn's stream is retired so its partial reply stays on screen and the redirect streams fresh.
            let watching = streaming
            let previous = streamTask
            previous?.cancel()
            await previous?.value
            guard generation == current, selected?.id == id else { return true }
            streaming = false
            let partial = watching ? interruptedReply(liveParts, model: selectedModel ?? selected?.model) : nil
            liveParts = []
            if var chat = selected {
                chat.messages = (chat.messages ?? []) + [partial].compactMap { $0 } + [ChatMessage(role: "user", content: text)]
                chat.isRunning = true
                selected = chat
                syncRunning(chat)
            }
            if foreground { observe(id, client: client) }
            return true
        } catch {
            if case ClientError.http(401) = error { handle(error) }
            else { self.error = String(localized: "Send could not be confirmed. Check the conversation before trying again.") }
            return false
        }
    }

    /// A button or form on a surface: a blocked question gets its answer, anything else is sent like a message.
    /// Returns whether the answer was delivered, so a form can be used again after a failure.
    func act(on surface: A2UISurface, action: String, context: [String: JSONValue]) async -> Bool {
        guard let client, device?.permissions.send == true, let id = selected?.id, !id.isEmpty else { return false }
        if surface.isDeferred {
            do {
                try await client.answerSurface(id, surfaceID: surface.id, answer: deferredAnswer(context))
                liveParts.removeAll { $0.type == "a2ui" && $0.surface?.id == surface.id }
                return true
            } catch {
                if case ClientError.http(401) = error { handle(error) }
                else { self.error = String(localized: "The answer could not be delivered. The question may have expired.") }
                return false
            }
        }
        let text = action == "submit_question" ? questionAnswerText(context)
            : canvasActionMessage(action: action, context: context, surfaceID: surface.id)
        guard !text.isEmpty else { return false }
        return await submit(text, outgoing: [], fromDraft: false)
    }

    private func submit(_ text: String, outgoing: [PendingAttachment], fromDraft: Bool) async -> Bool {
        guard let client, device?.permissions.send == true, var id = selected?.id, !busy, !streaming else { return false }
        guard !text.isEmpty || !outgoing.isEmpty else { return false }
        busy = true
        error = nil
        defer { busy = false }
        do {
            if id.isEmpty {
                guard device?.permissions.createChats == true else { return false }
                let created = try await client.createChat(title: String(localized: "Mobile conversation"), projectID: selected?.projectId)
                selected = created
                id = created.id
                UserDefaults.standard.set(selectedModel, forKey: "suzent.chatModel.\(origin).\(id)")
                chats.insert(created, at: 0)
            }
            let issued = outgoing.isEmpty ? [] : try await client.upload(outgoing, chatID: id)
            try await client.send(text, chatID: id, model: selectedModel, attachments: issued)
            if fromDraft { draft = ""; drafts[id] = nil }
            outgoing.forEach { try? FileManager.default.removeItem(at: $0.url) }
            attachments.removeAll { item in outgoing.contains { $0.id == item.id } }
            sentVersion += 1
            if var chat = selected, chat.id == id {
                chat.messages = (chat.messages ?? []) + [ChatMessage(role: "user", content: text,
                    files: outgoing.map { FileAttachment(filename: $0.name, mimeType: $0.mimeType) })]
                chat.isRunning = true
                selected = chat
                syncRunning(chat)
            }
            if foreground { observe(id, client: client) }
            return true
        } catch {
            if case ClientError.http(401) = error { handle(error) }
            else { self.error = String(localized: "Send could not be confirmed. Check the conversation before trying again.") }
            return false
        }
    }

    private func observe(_ id: String, client: any MobileClient) {
        guard !streaming, foreground else { return }
        streaming = true
        liveParts = []
        let current = generation
        let buffer = LiveActivityAccumulator()
        streamTask = Task {
            let publisher = Task { @MainActor in
                while !Task.isCancelled {
                    do { try await Task.sleep(for: .milliseconds(50)) } catch { return }
                    guard generation == current, foreground else { return }
                    await publishActivity(from: buffer, generation: current)
                }
            }
            defer { publisher.cancel() }
            do {
                try await client.observe(id) { [weak self] event in
                    await buffer.consume(event)
                    if event.type == "RUN_ERROR" { await self?.receive(event, generation: current) }
                }
                publisher.cancel()
                guard generation == current, !Task.isCancelled else { return }
                await publishActivity(from: buffer, generation: current)
                let saved = try await client.chat(id)
                guard generation == current, !Task.isCancelled, selected?.id == id else { return }
                selected = saved
                syncRunning(saved)
                liveParts = []
            } catch {
                if !Task.isCancelled, generation == current {
                    await publishActivity(from: buffer, generation: current)
                    if generation == current { handle(error) }
                }
            }
            guard generation == current, !Task.isCancelled else { return }
            streaming = false
        }
    }

    private func receive(_ event: StreamEvent, generation current: UUID) {
        guard generation == current, foreground else { return }
        if event.type == "RUN_ERROR" { error = event.message ?? String(localized: "Task failed.") }
    }

    private func publishActivity(from buffer: LiveActivityAccumulator, generation current: UUID) async {
        let parts = await buffer.drain()
        guard generation == current, foreground, !Task.isCancelled else { return }
        if let parts { liveParts = parts }
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
        guard !id.isEmpty else { return }
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
                        selected = saved; syncRunning(saved); liveParts = []
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
                self.error = String(localized: "Approval could not be confirmed. Check its status before trying again.")
            }
        }
    }

    func stop() async {
        guard !stopInFlight, device?.permissions.stop == true, let id = selected?.id, let client else { return }
        stopInFlight = true
        defer { stopInFlight = false }
        do { try await client.stop(id) }
        catch { handle(error) }
    }

    func setForeground(_ active: Bool) async {
        foreground = active
        if !active {
            connectionUpgrade.cancel()
            cancelReconnect()
            streamTask?.cancel()
            streaming = false
            liveParts = []
            disconnectNode()
        } else {
            if let relayed = client as? SuzentClient, relayed.relay != nil,
               let id = store.activeId, let saved = connection {
                startDirectUpgrade(id, saved, relayed)
            }
            if !connected && canReconnect { await connect() }
            await refresh()
            if let chat = selected, chat.isRunning == true, let client {
                observe(chat.id, client: client)
            }
            if nodeEnabled { startNode() }
        }
    }

    func toggleNode(_ enabled: Bool) {
        guard !isDemo else { return }
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
        guard !isDemo, let client = client as? SuzentClient, let desktopID = store.activeId, let connection, foreground else { return }
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
                        if let credential = value["device_token"] as? String, !credential.isEmpty, var saved = store.desktop(desktopID)?.connection {
                            saved.nodeToken = credential
                            try storeConnection(desktopID, saved)
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

    private func sendNode(_ value: [String: Any], to ws: any MobileSocket) async throws {
        let data = try JSONSerialization.data(withJSONObject: value)
        try await ws.send(.string(String(decoding: data, as: UTF8.self)))
    }

    func forget() {
        if isDemo { exitDemo(); return }
        if let id = store.activeId { forgetDesktop(id) } else { clearSession() }
    }

    /// Removes only this phone's credential for the desktop; revoking it remotely happens on the desktop.
    func forgetDesktop(_ id: String, reconnectNext: Bool = true) {
        guard !isDemo, let desktop = store.desktop(id) else { return }
        revokeOnDesktop(desktop.connection)
        // A switch still checking this desktop would otherwise activate an id that is no longer saved.
        if checkingDesktopId == id { reconnectTask?.cancel() }
        let wasActive = store.activeId == id
        var next = store
        next.remove(id)
        do { try CredentialStore.save(next) }
        catch { self.error = error.localizedDescription }
        store = next
        guard wasActive else { return }
        clearSession()
        if reconnectNext && canReconnect { Task { await connect(keepingError: true) } }
    }

    /// Best effort: otherwise the desktop keeps a grant no phone holds, and the next scan adds another.
    private func revokeOnDesktop(_ saved: Connection) {
        let direct = (try? Backend(saved.origin, allowHTTP: allowsHTTP)).flatMap {
            try? SuzentClient(backend: $0, token: saved.hostToken, deviceTrust: saved.tls)
        }
        let relayed = saved.relay.flatMap { try? SuzentClient(relay: $0, token: saved.hostToken) }
        Task {
            defer { direct?.close(); relayed?.close() }
            if let direct, (try? await direct.forgetPairing()) != nil { return }
            try? await relayed?.forgetPairing()
        }
    }

    private func resetSessionState() {
        connectionUpgrade.cancel()
        retiredClients.forEach { $0.close() }
        retiredClients = []
        voice.stop()
        voiceSupported = false
        scheduledTasks = []
        projects = []; selectedModel = nil; drafts = [:]; discardAttachments(); attachmentsSupported = false; overviewSupported = false; surfacesSupported = false; steerSupported = false
        discardQueues()
        pendingApprovals = []; approvalChoices = [:]; approvalBusy = false
        generation = UUID()
        nodeEnabled = false
        disconnectNode()
        streamTask?.cancel()
        streaming = false
        liveParts = []
        selected = nil
        chats = []
        chatPages = [:]; loadingPages = []; navigationRevision = UUID()
        device = nil
        draft = ""
    }

    private func clearSession() {
        pairingTask?.cancel()
        reconnectTask?.cancel()
        resetSessionState()
        client?.close()
        client = nil
        connected = false
        busy = false
        canReconnect = connection?.clientProtocol == 1
        pairingInvitation = nil
        awaitingDesktop = false
        invitationText = ""
        origin = connection?.origin ?? ""
    }
}
