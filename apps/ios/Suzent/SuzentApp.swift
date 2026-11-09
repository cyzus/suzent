import SwiftUI
import SuzentCore
import MarkdownUI

@main struct SuzentApp: App {
    @State private var model = MobileModel()
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            ContentView(model: model)
                .appPreferences()
                .onChange(of: phase) { _, phase in
                    if phase == .background { model.voice.stop() }
                    Task { await model.setForeground(phase == .active) }
                }
        }
    }
}

private enum Route: Hashable { case search, conversation }

private struct SidebarFoldAnchorKey: PreferenceKey {
    static var defaultValue: Anchor<CGRect>? { nil }
    static func reduce(value: inout Anchor<CGRect>?, nextValue: () -> Anchor<CGRect>?) {
        value = value ?? nextValue()
    }
}

private extension View {
    /// Keeps the Suzent sidebar look inside a plain List: no separators or row fill, page gutters.
    func sidebarListRow(_ vertical: CGFloat = 6) -> some View {
        listRowInsets(EdgeInsets(top: vertical, leading: 16, bottom: vertical, trailing: 16))
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)
    }
}

private struct SidebarFoldControl: View {
    let count: Int
    let expanded: Bool
    let toggle: () -> Void
    var body: some View {
        // Inline in the reserved meta slot: 16pt tall, widened horizontally for the tap target.
        Button(action: toggle) {
            HStack(spacing: 2) {
                Text("\(count) sub-agents")
                Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold))
                    .rotationEffect(.degrees(expanded ? 90 : 0))
            }.suzentFont(PresentationTokens.typeSidebarSection, weight: .medium).foregroundStyle(Color.suzentMuted)
                .padding(.horizontal, 4)
                .frame(minHeight: 16).contentShape(Rectangle())
        }.buttonStyle(.plain)
            .accessibilityLabel(expanded ? Text("Collapse sub-agents: \(count)") : Text("Expand sub-agents: \(count)"))
    }
}

/// Single-field text entry presented as a sheet with Cancel and Save in the toolbar.
private struct TextEntrySheet: View {
    let title: LocalizedStringKey
    let placeholder: LocalizedStringKey
    @Binding var text: String
    let save: () -> Void
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool
    private var valid: Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return !trimmed.isEmpty && trimmed.count <= 200
    }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading) {
                TextField(placeholder, text: $text).suzentFont(PresentationTokens.typeControl)
                    .focused($focused).submitLabel(.done)
                    .onSubmit { if valid { save(); dismiss() } }
                    .padding(PresentationTokens.spaceMedium).frame(minHeight: PresentationTokens.controlHeight)
                    .overlay(Rectangle().stroke(focused ? Color.suzentLink : Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                Spacer()
            }.padding(20)
                .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) { Button("Save") { save(); dismiss() }.disabled(!valid) }
                }
                .onAppear { focused = true }
        }.presentationDetents([.medium]).presentationCornerRadius(PresentationTokens.radius)
    }
}

private struct ChatSidebarRow: View {
    let chat: Chat
    let selected: Bool
    let parentTitle: String?
    let nested: Bool
    let childCount: Int
    let childrenExpanded: Bool
    let toggleChildren: () -> Void
    let enabled: Bool
    let canManage: Bool
    let projects: [Project]
    let manage: (String, String?) -> Void
    let open: () -> Void
    @State private var renaming = false
    @State private var deleting = false
    @State private var title = ""
    @State private var swipedPin = 0
    @State private var swipedDelete = 0
    private var pinned: Bool { chat.pinned == true }
    private var running: Bool { chat.isRunning == true }
    private var swipeable: Bool { enabled && canManage && !running }

    private var meta: Text? {
        if chat.isSubagent && !nested { return parentTitle.map { Text("Sub-agent of \($0)") } ?? Text("Sub-agent") }
        if chat.isScheduled { return Text("Scheduled task") }
        return chat.projectName.map { Text($0) }
    }

    var body: some View {
        Button(action: open) {
            HStack(spacing: 6) {
                if pinned { Image(systemName: "pin.fill").font(.system(size: 10)) }
                VStack(alignment: .leading, spacing: 0) {
                    Text(chat.title).suzentFont(PresentationTokens.typeCaption, weight: .medium)
                        .lineLimit(1).truncationMode(.tail)
                    HStack(spacing: 0) {
                        if let meta { meta.lineLimit(1).truncationMode(.tail) }
                        if meta != nil && childCount > 0 { Text(" · ") }
                        if childCount > 0 {
                            SidebarFoldControl(count: childCount, expanded: childrenExpanded, toggle: {}).hidden()
                                .anchorPreference(key: SidebarFoldAnchorKey.self, value: .bounds) { $0 }
                        }
                    }.suzentFont(PresentationTokens.typeSidebarSection, weight: .medium)
                        .foregroundStyle(Color.suzentMuted)
                        .frame(minHeight: meta != nil || childCount > 0 ? 16 : 0)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Spacer(minLength: 0)
                if running { Image(systemName: "ellipsis") }
            }.padding(.leading, nested ? 32 : 12).padding(.trailing, 12).padding(.vertical, PresentationTokens.spaceRow)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(ChatRowButtonStyle(selected: selected)).disabled(!enabled)
            // The fold control sits over a hidden placeholder so it is not a button nested inside the row button.
            .overlayPreferenceValue(SidebarFoldAnchorKey.self) { anchor in
                GeometryReader { proxy in
                    if let anchor {
                        let rect = proxy[anchor]
                        SidebarFoldControl(count: childCount, expanded: childrenExpanded, toggle: toggleChildren)
                            .frame(width: rect.width, height: rect.height)
                            .offset(x: rect.minX, y: rect.minY)
                    }
                }
            }
            .contentShape(.contextMenuPreview, Rectangle())
            .contextMenu { if enabled { menuItems } }
            .swipeActions(edge: .leading, allowsFullSwipe: true) {
                if swipeable {
                    Button { swipedPin += 1; manage(pinned ? "unpin" : "pin", nil) } label: {
                        Label(pinned ? LocalizedStringKey("Unpin") : LocalizedStringKey("Pin"), systemImage: pinned ? "pin.slash" : "pin")
                    }.tint(pinned ? Color.suzentMuted : Color(presentation: PresentationTokens.blue))
                }
            }
            .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                if swipeable {
                    // Not role: .destructive, which would animate the row away before the confirmation.
                    Button { swipedDelete += 1; deleting = true } label: { Label("Delete", systemImage: "trash") }
                        .tint(Color.suzentDanger)
                }
            }
            .suzentFeedback(.success, trigger: swipedPin)
            .suzentFeedback(.warning, trigger: swipedDelete)
            .accessibilityActions {
                if enabled && canManage {
                    Button("Rename") { startRename() }
                }
            }
            .sheet(isPresented: $renaming) {
                TextEntrySheet(title: "Rename", placeholder: "Conversation title", text: $title) {
                    manage("rename", title.trimmingCharacters(in: .whitespacesAndNewlines))
                }
            }
            .alert("Delete conversation?", isPresented: $deleting) {
                Button("Cancel", role: .cancel) {}
                Button("Delete", role: .destructive) { manage("delete", nil) }
            } message: { Text("This deletes the conversation on all devices and cannot be undone.") }
    }

    @ViewBuilder private var menuItems: some View {
        if !canManage {
            Button("Enable Manage conversations in desktop Settings → Mobile access.") {}.disabled(true)
        } else {
            Button { manage(pinned ? "unpin" : "pin", nil) } label: {
                Label(pinned ? LocalizedStringKey("Unpin") : LocalizedStringKey("Pin"), systemImage: pinned ? "pin.slash" : "pin")
            }
            Button { startRename() } label: { Label("Rename", systemImage: "pencil") }
            Menu {
                ForEach(projects) { project in
                    Button { manage("move", project.id) } label: {
                        if project.id == chat.projectId { Label(project.name, systemImage: "checkmark") } else { Text(project.name) }
                    }.disabled(project.id == chat.projectId)
                }
            } label: { Label("Move to project", systemImage: "folder") }
                .disabled(running || projects.isEmpty)
            Divider()
            Button(role: .destructive) { deleting = true } label: { Label("Delete conversation", systemImage: "trash") }
                .disabled(running)
        }
    }

    private func startRename() {
        title = chat.title
        renaming = true
    }
}

struct ContentView: View {
    @Bindable var model: MobileModel
    @State private var path: [Route] = []
    @State private var transcriptCache = ChatPresentationCache()
    @State private var showSettings = false
    @State private var repairScanner = false
    @State private var showConnectionHelp = false
    @State private var confirmForget = false
    @State private var search = ""
    /// The phone search page's query; the inline `search` field only exists on wide layouts.
    @State private var searchText = ""
    @State private var expandedProject: String? = nil
    @AppStorage("homeListMode") private var listMode: HomeListMode = .recent
    @State private var expandedAgents: Set<String> = []
    @State private var regentPressed = false
    @State private var tab: HomeTab = .chats
    @State private var sidebarVisibility: NavigationSplitViewVisibility = .all
    @FocusState private var composing: Bool
    @State private var keyboardVisible = false
    @State private var attachmentsExpanded = false
    @State private var railChoices = RailChoices()
    @State private var streamGeneration = 0
    @State private var sawStreaming = false
    @State private var showModelPicker = false
    @State private var showProjectPicker = false
    @State private var showInfo = false
    @State private var sends = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var wide: Bool { sizeClass == .regular }

    private var conversationVisible: Bool {
        model.connected && !showSettings && model.selected != nil && (wide || path.last == .conversation)
    }

    private var projects: [Project] {
        // Android dedupes the merged list; keep the same guarantee so duplicate ids
        // cannot reach ForEach identity or the activity lookup.
        var result: [Project] = []
        for project in model.projects where !result.contains(where: { $0.id == project.id }) {
            result.append(project)
        }
        for chat in model.chats {
            if let id = chat.projectId, !result.contains(where: { $0.id == id }) {
                result.append(Project(id: id, name: chat.projectName ?? id))
            }
        }
        // The recent page is newest-first (updated_at desc), so a project's earliest chat index
        // there is its latest activity. Mirrors the desktop sidebar's sortedProjects ordering
        // without adding a timestamp to the mobile payload. model.chats is not ranked: opening a
        // project appends its page there, which would reorder the projects on every expand.
        var activity: [String: Int] = [:]
        for (index, chat) in model.pageChats(ChatPageQuery()).enumerated() {
            guard let id = chat.projectId, activity[id] == nil else { continue }
            activity[id] = index
        }
        var serverOrder: [String: Int] = [:]
        for (index, project) in result.enumerated() where serverOrder[project.id] == nil { serverOrder[project.id] = index }
        return result.sorted { lhs, rhs in
            let left = activity[lhs.id] ?? Int.max
            let right = activity[rhs.id] ?? Int.max
            if left != right { return left < right }
            return (serverOrder[lhs.id] ?? 0) < (serverOrder[rhs.id] ?? 0)
        }
    }

    var body: some View {
        Group {
            if !model.connected { unconnected }
            else if wide {
                NavigationSplitView(columnVisibility: $sidebarVisibility) {
                    sidebar(home: false)
                        .navigationSplitViewColumnWidth(PresentationTokens.sidebarWidth)
                        .toolbar(removing: .sidebarToggle)
                } detail: {
                    NavigationStack { detail }
                }.navigationSplitViewStyle(.balanced)
            } else {
                NavigationStack(path: $path) {
                    VStack(spacing: 0) {
                        switch tab {
                        case .chats: sidebar(home: true)
                        case .tasks: tasksTab
                        case .settings: settingsTab
                        }
                        HomeTabBar(selection: $tab)
                    }.ignoresSafeArea(.keyboard, edges: .bottom)
                        .toolbar(.hidden, for: .navigationBar)
                        .navigationDestination(for: Route.self) { route in
                            switch route {
                            case .search: searchPage
                            case .conversation: detail
                            }
                        }
                }
            }
        }
        .background(Color.suzentBackground)
        .foregroundStyle(Color.suzentText)
        // The compact home keeps its tab bar uncovered.
        .overlay(alignment: .bottom) { toastHost(!conversationVisible).padding(.bottom, !wide && model.connected && path.isEmpty ? 56 : 0) }
        .task { if model.canReconnect && !model.connected { await model.connect() } }
        .tint(Color.suzentText)
        .task(id: model.connected) { if model.connected { await model.watchNavigation() } }
        .task(id: model.error) {
            guard let error = model.error else { return }
            AccessibilityNotification.Announcement(error).post()
            try? await Task.sleep(for: .seconds(6))
            if !Task.isCancelled && model.error == error { model.error = nil }
        }
        .onChange(of: model.selected?.isRegent == true && conversationVisible, initial: true) { _, visible in
            model.regentVisible = visible
        }
        .onChange(of: model.connected) { _, connected in
            showModelPicker = false; showProjectPicker = false; path = []
            if !connected { showSettings = false }
        }
        .onChange(of: path) { _, path in
            if path.isEmpty { composing = false; attachmentsExpanded = false }
            if !path.contains(.search) { searchText = "" }
            if path.last != .conversation { showInfo = false }
        }
        .onChange(of: model.activeDesktopId) { _, _ in
            search = ""; searchText = ""; expandedProject = nil; expandedAgents = []
            if !path.isEmpty { path = [] }
        }
        .onChange(of: model.selected == nil) { _, missing in
            if missing && path.last == .conversation { path.removeLast() }
        }
        .onChange(of: wide) { _, wide in
            if wide {
                showSettings = tab == .settings
            } else {
                if showSettings { tab = .settings }
                showSettings = false
                path = tab != .settings && model.selected != nil ? [.conversation] : []
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in keyboardVisible = true }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in keyboardVisible = false }
        .sheet(isPresented: $showModelPicker) {
            SuzentSelectionPanel(title: String(localized: "Desktop model"),
                options: [(id: "", title: String(localized: "Conversation default"))] + Array(Set(model.selected?.models ?? [])).sorted().map { (id: $0, title: $0) },
                selected: model.selectedModel ?? "", dismiss: { showModelPicker = false }) {
                    model.selectModel($0.isEmpty ? nil : $0)
                }
        }
        .sheet(isPresented: $showProjectPicker) {
            SuzentSelectionPanel(title: String(localized: "Creating in"),
                options: model.projects.map { (id: $0.id, title: $0.name) },
                selected: model.selected?.projectId ?? "", dismiss: { showProjectPicker = false }) { id in
                    model.selected?.projectId = id
                    model.selected?.projectName = model.projects.first { $0.id == id }?.name
                }
        }
        .suzentFeedback(.impact(weight: .light), trigger: sends)
        .onChange(of: model.isDemo) { _, _ in
            showSettings = false; path = []; tab = .chats; showModelPicker = false; showProjectPicker = false; composing = false
        }
        .onChange(of: model.sentVersion) { _, _ in composing = false }
        .fullScreenCover(isPresented: $repairScanner) { PairingScanner(model: model) }
    }

    @ViewBuilder private func toastHost(_ visible: Bool) -> some View {
        ZStack {
            if visible, let error = model.error {
                SuzentErrorToast(message: error) { model.error = nil }
                    .transition(reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity))
            }
        }.animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: model.error)
    }

    private func showConversation() {
        composing = false
        showSettings = false
        // Opened from the search page, back returns to the results.
        if !wide && path.last != .conversation { path = path.last == .search ? [.search, .conversation] : [.conversation] }
    }

    private func openSettings() {
        composing = false
        if wide { showSettings = true } else { tab = .settings; path = [] }
    }

    private func newConversation() {
        composing = false
        Task {
            await model.createChat()
            if model.selected != nil { showConversation() }
        }
    }

    private var unconnected: some View {
        VStack(spacing: 0) {
            Group {
                if model.canReconnect {
                    Text("SUZENT").tracking(2).suzentFont(13, weight: .semibold)
                        .foregroundStyle(Color.suzentMuted).frame(maxWidth: .infinity, alignment: .leading)
                } else { SuzentWordmark() }
            }.frame(maxWidth: .infinity, minHeight: PresentationTokens.controlHeight)
                .padding(.horizontal, 12).padding(.vertical, 6)
            if model.canReconnect {
                VStack {
                    Spacer(minLength: 20)
                    VStack(spacing: 21) {
                        ReconnectIndicator(active: model.busy, stage: model.reconnectStage)
                        Text(model.busy ? String(localized: "Connecting to Suzent") : String(localized: "Reconnect to desktop"))
                            .suzentFont(21, weight: .medium).multilineTextAlignment(.center)
                        VStack(spacing: 6) {
                            if let desktop = model.desktops.first(where: { $0.id == (model.checkingDesktopId ?? model.activeDesktopId) }) {
                                HStack(spacing: 6) {
                                    Image(systemName: "desktopcomputer").font(.system(size: 12, weight: .medium))
                                    Text(desktop.name).lineLimit(1)
                                }.suzentFont(PresentationTokens.typeCaption, weight: .medium).foregroundStyle(Color.suzentMuted)
                            }
                            Group {
                                Text(model.busy ? (model.reconnectStatus ?? "") : "").suzentFont(PresentationTokens.typeCaption, weight: .semibold, design: .monospaced)
                                    .tracking(0.8).foregroundStyle(Color.suzentMuted).lineLimit(1)
                            }.frame(height: 16)
                        }
                        Group {
                            if model.busy {
                                if model.reconnecting { Button("Cancel") { model.cancelReconnect() } }
                            } else { Button("Reconnect to desktop") { Task { await model.connect() } } }
                        }.suzentFont(PresentationTokens.typeCaption).foregroundStyle(Color.suzentMuted)
                            .buttonStyle(.plain).frame(minHeight: 44)
                    }
                    Spacer(minLength: 20)
                    otherDesktops
                    HStack {
                        Button("Pair another desktop") {
                            model.cancelReconnect(); model.beginPairing(repairActive: false); repairScanner = true
                        }.disabled(model.busy && !model.reconnecting)
                        Spacer(minLength: 12)
                        Button("Connection help") { showConnectionHelp = true }
                    }.suzentFont(PresentationTokens.typeLabel).foregroundStyle(Color.suzentMuted)
                        .frame(minHeight: 44).buttonStyle(.plain)
                }.padding(.horizontal, 24).padding(.bottom, 20)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .confirmationDialog("Connection help", isPresented: $showConnectionHelp, titleVisibility: .visible) {
                        Button("Pair again") { model.beginPairing(repairActive: true); repairScanner = true }.disabled(model.busy || model.streaming)
                        Button("Forget connection", role: .destructive) { model.forget() }.disabled(model.busy)
                        Button("Cancel", role: .cancel) { }
                    } message: { Text("Check that Suzent is running on your desktop and both devices are online.") }
            } else {
                Rectangle().fill(Color.suzentOutline).frame(height: PresentationTokens.borderWidth)
                PairingView(model: model)
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity).background(Color.suzentBackground)
    }

    /// Visible on the reconnect screen so an unreachable default desktop never hides the others behind a menu.
    @ViewBuilder private var otherDesktops: some View {
        let others = model.desktops.filter { $0.id != model.activeDesktopId }
        if !others.isEmpty {
            VStack(alignment: .leading, spacing: 0) {
                Text("Other desktops").suzentFont(PresentationTokens.typeLabel).foregroundStyle(Color.suzentMuted)
                    .padding(.bottom, 6)
                Rectangle().fill(Color.suzentOutline).frame(height: PresentationTokens.borderWidth)
                ViewThatFits(in: .vertical) {
                    desktopRows(others)
                    ScrollView { desktopRows(others) }.frame(maxHeight: 220)
                }
            }
        }
    }

    private func desktopRows(_ desktops: [SavedDesktop]) -> some View {
        VStack(spacing: 0) {
            ForEach(desktops) { desktop in
                // Tappable while the default desktop is still being tried: the switch abandons that attempt.
                Button { Task { await model.switchDesktop(desktop.id) } } label: {
                    HStack(spacing: 12) {
                        DesktopSwatch(desktop: desktop, size: 12)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(desktop.name).suzentFont(PresentationTokens.typeControl, weight: .semibold)
                                .foregroundStyle(Color.suzentText).lineLimit(1)
                            Text(displayOrigin(desktop.connection.origin)).font(.caption.monospaced())
                                .foregroundStyle(Color.suzentMuted).lineLimit(1).truncationMode(.middle)
                        }
                        Spacer(minLength: 8)
                    }.frame(minHeight: 52).contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .disabled(model.busy && !model.reconnecting)
                    .accessibilityLabel("Switch to \(desktop.name)")
                Rectangle().fill(Color.suzentOutline.opacity(0.5)).frame(height: PresentationTokens.borderWidth)
            }
        }
    }

    @ViewBuilder private var detail: some View {
        Group {
            if showSettings { settings.navigationTitle("Settings") }
            else if let chat = model.selected { conversation(chat) }
            else if model.busy { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
            else {
                Text("Select a conversation or start a new one.").foregroundStyle(Color.suzentMuted)
                    .padding().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(Color.suzentBackground)
        // A trailing column on iPad and a resizable sheet on iPhone, from the same panel.
        .inspector(isPresented: Binding(get: { showInfo && infoAvailable }, set: { showInfo = $0 })) {
            if let id = model.selected?.id {
                ChatInfoPanel(model: model, chatID: id)
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
                    .inspectorColumnWidth(min: 280, ideal: PresentationTokens.sidebarWidth, max: 420)
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbarRole(.editor)
        .toolbar {
            if wide && sidebarVisibility == .detailOnly {
                ToolbarItem(placement: .topBarLeading) {
                    Button { withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.25)) { sidebarVisibility = .all } } label: {
                        Image(systemName: "sidebar.left")
                    }.accessibilityLabel("Show sidebar")
                }
            }
            if !showSettings {
                ToolbarItem(placement: .principal) { conversationTitle.dynamicTypeSize(...DynamicTypeSize.accessibility3) }
                if infoAvailable { ToolbarItem(placement: .topBarTrailing) {
                    Button { showInfo.toggle() } label: { PanelToggleIcon(open: showInfo, edge: wide ? .trailing : .bottom) }
                        .accessibilityLabel("Conversation info")
                        .accessibilityAddTraits(showInfo ? .isSelected : [])
                } }
                if !sidebarShown { ToolbarItem(placement: .topBarTrailing) {
                    Button(action: newConversation) { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("New conversation")
                        .disabled(model.busy || model.device?.permissions.createChats != true)
                } }
            }
        }
    }

    /// Regent's plan is the desktop board across conversations, so only ordinary saved chats get the panel.
    private var infoAvailable: Bool {
        guard let chat = model.selected, !showSettings else { return false }
        return model.overviewSupported && !chat.id.isEmpty && !chat.isRegent
    }

    /// The iPad sidebar already carries the wordmark and the create button.
    private var sidebarShown: Bool { wide && sidebarVisibility != .detailOnly }

    @ViewBuilder private var conversationTitle: some View {
        if let chat = model.selected, !chat.id.isEmpty {
            if chat.isRegent {
                RegentIdentity(working: model.streaming || chat.isRunning == true, waiting: chat.regent?.waiting ?? 0)
            } else {
                VStack(spacing: 2) {
                    if let project = chat.projectName {
                        Text(project).font(.caption).foregroundStyle(Color.suzentMuted).lineLimit(1)
                    }
                    Text(chat.title).suzentFont(PresentationTokens.typeControl, weight: .semibold)
                        .lineLimit(1).truncationMode(.tail)
                }.padding(.horizontal, 8).multilineTextAlignment(.center)
            }
        } else if !sidebarShown { SuzentWordmark() }
    }

    private func sidebar(home: Bool) -> some View {
        let searchQuery = ChatPageQuery("search", value: search.trimmingCharacters(in: .whitespacesAndNewlines))
        let recentRows = sidebarChats(model.pageChats(ChatPageQuery()), search: "", expanded: expandedAgents)
        let pinnedRows = sidebarChats(model.pageChats(ChatPageQuery("pinned")), search: "", expanded: expandedAgents)
        // Phones keep scheduled tasks in their own tab.
        let mode: HomeListMode = home && listMode == .tasks ? .recent : listMode
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                // The wordmark, not the logo face: Regent's row right below already shows the face.
                SuzentWordmark()
                Spacer()
                if home {
                    // Phones search on their own page, so results never share the screen with the home list.
                    Button { path = [.search] } label: {
                        Image(systemName: "magnifyingglass").font(.system(size: 20, weight: .medium)).frame(width: 44, height: 44)
                    }.buttonStyle(.plain).accessibilityLabel("Search chats")
                    newConversationIcon
                } else {
                    HStack(spacing: 2) {
                        Button { withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.25)) { sidebarVisibility = .detailOnly } } label: {
                            Image(systemName: "sidebar.left").font(.system(size: 18)).frame(width: 44, height: 44)
                        }.buttonStyle(.plain).accessibilityLabel("Hide sidebar")
                        Button(action: openSettings) {
                            Image(systemName: "gearshape").font(.system(size: 20)).frame(width: 44, height: 44)
                        }.buttonStyle(.plain).accessibilityLabel("Settings")
                        newConversationIcon
                    }
                }
            }.frame(minHeight: 44).padding(.leading, 20).padding(.trailing, home ? 20 : 14).padding(.top, 4).padding(.bottom, home ? 0 : 4)
                .dynamicTypeSize(...DynamicTypeSize.accessibility3)
            if let desktop = model.activeDesktop, !model.isDemo {
                activeDesktopLine(desktop).padding(.horizontal, 20).padding(.bottom, 4)
            }
            if let regent = model.chats.first(where: { $0.isRegent }) {
                Button { openSidebarChat(regent) } label: {
                    RegentIdentity(working: regent.isRunning == true || (model.selected?.isRegent == true && model.streaming),
                                   waiting: regent.regent?.waiting ?? 0, unread: model.selected?.isRegent == true ? 0 : regent.regent?.unread ?? 0,
                                   lastMessageAt: regent.regent?.lastMessageAt, expanded: false, coronation: regentPressed)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 14).padding(.horizontal, 4)
                        .overlay(alignment: .trailing) { Image(systemName: "chevron.right").font(.system(size: 12)).foregroundStyle(Color.suzentMuted) }
                        .overlay(alignment: .bottom) { Rectangle().fill(Color.suzentText.opacity(0.08)).frame(height: 1) }
                }.buttonStyle(PressReportingButtonStyle(pressed: $regentPressed)).disabled(model.busy).padding(.horizontal, 16)
            }
            if !home {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass").font(.system(size: 14, weight: .medium))
                    TextField("Search chats", text: $search).suzentFont(14)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                    if !search.isEmpty {
                        Button { search = "" } label: { Image(systemName: "xmark").font(.system(size: 12, weight: .semibold)) }
                            .buttonStyle(.plain).frame(minWidth: 28, minHeight: 36).accessibilityLabel("Clear search")
                    }
                }.padding(.horizontal, 10).frame(minHeight: 38)
                    .background(Color.suzentBackground)
                    .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: 1))
                    .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
            }
            if search.isEmpty {
                HomeListPicker(selection: $listMode, modes: home ? [.recent, .projects] : [.recent, .projects, .tasks])
                    .padding(.horizontal, 16).padding(.top, home ? 12 : 0).padding(.bottom, 4)
            }
            ScrollViewReader { reader in
                List {
                    Color.clear.frame(height: 0).id("sidebar-top").sidebarListRow(0).accessibilityHidden(true)
                    if !search.isEmpty {
                        sidebarHeading("Search results").sidebarListRow()
                        let rows = sidebarChats(model.pageChats(searchQuery), search: search, expanded: expandedAgents)
                        conversationRows(rows, scope: "search")
                        pageFooter(searchQuery)
                        if rows.isEmpty && model.chatPages[searchQuery] != nil {
                            Text("No matching chats").font(.subheadline).foregroundStyle(Color.suzentMuted).sidebarListRow()
                        }
                    } else {
                        switch mode {
                        case .recent:
                            if !pinnedRows.isEmpty {
                                sidebarHeading("Pinned").sidebarListRow()
                                conversationRows(pinnedRows, scope: "pinned")
                                pageFooter(ChatPageQuery("pinned"))
                                if !recentRows.isEmpty { sidebarHeading("Recent").sidebarListRow() }
                            }
                            conversationRows(recentRows, scope: "recent")
                            pageFooter(ChatPageQuery())
                            if pinnedRows.isEmpty && recentRows.isEmpty {
                                Text("No chats yet").font(.subheadline).foregroundStyle(Color.suzentMuted).padding(.vertical, 24).sidebarListRow()
                            }
                        case .projects:
                            ForEach(projects) { project in projectSection(project) }
                            if projects.isEmpty {
                                Text("No projects yet").font(.subheadline).foregroundStyle(Color.suzentMuted).padding(.vertical, 24).sidebarListRow()
                            }
                        case .tasks:
                            taskRows(scope: "scheduled")
                        }
                    }
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
                .environment(\.defaultMinListRowHeight, 0)
                .refreshable { await model.refresh() }
                .task(id: "\(search):\(model.navigationVersion)") {
                    guard !search.isEmpty else { return }
                    do { try await Task.sleep(for: .milliseconds(300)); try Task.checkCancellation() }
                    catch { return }
                    await model.loadPage(searchQuery)
                }
                .onChange(of: model.selected?.id) { _, _ in expandSelectedAgents() }
                .onChange(of: model.chats.map(\.id)) { _, _ in expandSelectedAgents() }
                .onChange(of: model.pinnedVersion) { _, _ in
                    withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.22)) {
                        reader.scrollTo("sidebar-top", anchor: .top)
                    }
                }
            }
        }
        .background(Color.suzentSurface)
        // The list keeps its branded header; pushed pages use the system bar and its back gesture.
        .toolbar(.hidden, for: .navigationBar)
    }

    /// The sidebar header's create button, shared by the phone home and the iPad sidebar; drawn like the
    /// header's other icons so nothing in the header is heavier than the rest.
    private var newConversationIcon: some View {
        Button(action: newConversation) {
            Image(systemName: "square.and.pencil").font(.system(size: 20, weight: .medium))
                .frame(width: 44, height: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityLabel("New conversation")
            .disabled(model.busy || model.device?.permissions.createChats != true)
    }

    private var searchPage: some View {
        let term = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        let query = ChatPageQuery("search", value: term)
        return VStack(spacing: 0) {
            HStack(spacing: 12) {
                SearchPageField(text: $searchText)
                Button("Cancel") { path = [] }.buttonStyle(.plain).frame(minHeight: 44)
            }.padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 8)
                .dynamicTypeSize(...DynamicTypeSize.accessibility3)
            List {
                if term.isEmpty {
                    Text("Search the titles of every chat this phone can read.")
                        .font(.subheadline).foregroundStyle(Color.suzentMuted).padding(.vertical, 24).sidebarListRow()
                } else {
                    let rows = sidebarChats(model.pageChats(query), search: term, expanded: expandedAgents)
                    conversationRows(rows, scope: "search")
                    pageFooter(query)
                    if rows.isEmpty && model.chatPages[query] != nil {
                        Text("No matching chats").font(.subheadline).foregroundStyle(Color.suzentMuted).sidebarListRow()
                    }
                }
            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .scrollDismissesKeyboard(.immediately)
            .environment(\.defaultMinListRowHeight, 0)
            .task(id: "\(term):\(model.navigationVersion)") {
                guard !term.isEmpty else { return }
                do { try await Task.sleep(for: .milliseconds(300)); try Task.checkCancellation() }
                catch { return }
                await model.loadPage(query)
            }
        }
        .background(Color.suzentSurface)
        .toolbar(.hidden, for: .navigationBar)
    }

    @ViewBuilder private func pageFooter(_ query: ChatPageQuery) -> some View {
        if model.loadingPages.contains(query) {
            ProgressView().frame(maxWidth: .infinity, minHeight: 44).accessibilityLabel("Loading conversations").sidebarListRow()
        } else if model.chatPages[query]?.nextOffset != nil || model.chatPages[query] == nil {
            Button("Load more") { Task { await model.loadPage(query, more: model.chatPages[query] != nil) } }
                .font(.caption).foregroundStyle(Color.suzentMuted).frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle()).buttonStyle(.plain).sidebarListRow()
        }
    }

    @ViewBuilder private func projectSection(_ project: Project) -> some View {
        let query = ChatPageQuery("project", value: project.id)
        let rows = sidebarChats(model.pageChats(query), search: "", expanded: expandedAgents)
        let projectOpen = expandedProject == project.id
        let isOpen = projectOpen || !search.isEmpty
        Button {
            expandedProject = projectOpen ? nil : project.id
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "folder").font(.system(size: 18)).padding(.trailing, 6)
                Text(project.name).lineLimit(1).truncationMode(.tail)
                Spacer()
                Text("\(project.chatCount ?? rows.count)").font(.caption).foregroundStyle(Color.suzentMuted)
                Image(systemName: isOpen ? "chevron.down" : "chevron.right").font(.system(size: 10)).foregroundStyle(Color.suzentMuted)
            }
            .suzentFont(PresentationTokens.typeCaption, weight: .semibold)
            .foregroundStyle(Color.suzentText)
            .padding(.horizontal, 4)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        }.buttonStyle(SuzentRowButtonStyle())
            .accessibilityValue(isOpen ? Text("Expanded") : Text("Collapsed"))
            .sidebarListRow(1)
            .task(id: "\(isOpen):\(model.navigationVersion)") {
                if isOpen { await model.loadPage(query) }
            }
        if isOpen {
            conversationRows(rows, scope: "project:\(project.id)", spacing: 0)
            pageFooter(query)
        }
    }

    /// One List holds every section and a chat can sit in several (Recent and its project), so row
    /// identity is scoped per section; a shared chat id makes the List reorder rows on expand.
    private func conversationRows(_ entries: [SidebarChatEntry], scope: String, spacing: CGFloat = 6) -> some View {
        ForEach(entries.map { ("\(scope):\($0.id)", $0) }, id: \.0) { item in
            let entry = item.1
            let chat = entry.chat
            ChatSidebarRow(chat: chat, selected: wide && model.selected?.id == chat.id && !showSettings,
                           parentTitle: model.chats.first { $0.id == chat.parentChatId }?.title,
                           nested: entry.depth > 0, childCount: entry.childCount, childrenExpanded: expandedAgents.contains(chat.id),
                           toggleChildren: {
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.16)) {
                    if expandedAgents.contains(chat.id) { expandedAgents.remove(chat.id) }
                    else { expandedAgents.insert(chat.id) }
                }
            },
                           enabled: !model.busy, canManage: model.device?.permissions.manageChats == true,
                           projects: model.projects, manage: { action, value in
                Task { await model.manageChat(chat, action: action, value: value) }
            }) { openSidebarChat(chat) }
                .sidebarListRow(spacing)
        }
    }

    private func openSidebarChat(_ chat: Chat) {
        showConversation()
        Task { await model.open(chat) }
    }

    private func expandSelectedAgents() {
        var current = model.chats.first { $0.id == model.selected?.id }
        var parents = Set<String>()
        while let chat = current, chat.isSubagent, let parent = chat.parentChatId, parents.insert(parent).inserted {
            current = model.chats.first { $0.id == parent }
        }
        expandedAgents.formUnion(parents)
    }

    private func sidebarHeading(_ title: LocalizedStringKey) -> some View {
        Text(title).textCase(.uppercase).tracking(1.6)
            .suzentFont(PresentationTokens.typeSidebarSection, weight: .heavy)
            .foregroundStyle(Color.suzentMuted)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityAddTraits(.isHeader)
    }

    /// Desktop status line order: paused (with failure) → failed → next run → active;
    /// a running task keeps the marker and still reports the schedule.
    private func scheduledTaskStatus(_ task: ScheduledTask) -> String {
        if !task.active { return task.unresolvedError ? String(localized: "Paused · Failed") : String(localized: "Paused") }
        if task.unresolvedError { return String(localized: "Last run failed") }
        if let raw = task.nextRunAt, let date = suzentParseDate(raw) {
            return String(localized: "Next run: \(date.suzentStamp)")
        }
        return String(localized: "Active")
    }

    private func scheduledTaskActivity(_ task: ScheduledTask) -> String {
        let raw = task.failureHandled ? task.chatUpdatedAt : task.lastRunAt
        return raw.flatMap(suzentParseDate)?.suzentStamp ?? String(localized: "Not yet")
    }

    private func scheduledTaskRow(_ task: ScheduledTask, root: SidebarChatEntry?) -> some View {
        Button {
            if let id = task.chatId { openSidebarChat(model.chats.first { $0.id == id } ?? Chat(id: id, title: task.name)) }
        } label: {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 0) {
                    Text(task.name).suzentFont(PresentationTokens.typeCaption, weight: .medium)
                        .lineLimit(1).truncationMode(.tail)
                    HStack(spacing: 6) {
                        if task.isRunning { Rectangle().fill(Color.suzentLink).frame(width: 8, height: 8) }
                        Text(scheduledTaskStatus(task)).lineLimit(1).truncationMode(.tail)
                        if let root, root.childCount > 0 {
                            Text("·")
                            SidebarFoldControl(count: root.childCount, expanded: expandedAgents.contains(root.id), toggle: {}).hidden()
                                .anchorPreference(key: SidebarFoldAnchorKey.self, value: .bounds) { $0 }
                        }
                    }.suzentFont(PresentationTokens.typeSidebarSection, weight: .medium)
                        .foregroundStyle(Color.suzentMuted)
                    if task.chatId == nil {
                        Text("No conversation yet").suzentFont(PresentationTokens.typeSidebarSection, weight: .medium)
                            .foregroundStyle(Color.suzentMuted)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
                Text(scheduledTaskActivity(task))
                    .suzentFont(PresentationTokens.typeSidebarSection, weight: .medium).monospacedDigit()
                    .foregroundStyle(Color.suzentMuted).lineLimit(1).padding(.leading, 8)
            }.padding(.horizontal, 12).padding(.vertical, PresentationTokens.spaceRow).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        }.buttonStyle(ChatRowButtonStyle(selected: wide && task.chatId != nil && model.selected?.id == task.chatId && !showSettings))
            .disabled(model.busy || task.chatId == nil)
            .overlayPreferenceValue(SidebarFoldAnchorKey.self) { anchor in
                GeometryReader { proxy in
                    if let anchor, let root {
                        let rect = proxy[anchor]
                        SidebarFoldControl(count: root.childCount, expanded: expandedAgents.contains(root.id)) {
                            if expandedAgents.contains(root.id) { expandedAgents.remove(root.id) }
                            else { expandedAgents.insert(root.id) }
                        }
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX, y: rect.minY)
                    }
                }
            }
    }

    private var settings: some View {
        Form {
            if model.isDemo {
                Section {
                    Button("Reset demo") { Task { await model.resetDemo() } }.disabled(model.busy)
                    Button("Exit demo") { model.exitDemo() }.disabled(model.busy)
                } footer: {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Explore with sample data. No desktop, API key, or internet required.")
                        Text("Pairing and Node connections require a real desktop. Attachments stay on this device and are not analysed.")
                    }.foregroundStyle(Color.suzentMuted)
                }
            } else {
                if let desktop = model.activeDesktop {
                    Section {
                        NavigationLink {
                            DesktopsPage(model: model) { repairScanner = true }
                        } label: {
                            DesktopCard(desktop: desktop, origin: model.origin, count: model.desktops.count)
                        }
                    } header: { settingsHeader("Connection") }
                }
                // Everything here applies to the connected desktop only, so it lives in one section.
                Section {
                    NavigationLink {
                        ScrollView {
                            if let device = model.device {
                                ClientPermissionsView(device: device, origin: model.origin)
                                    .frame(maxWidth: .infinity, alignment: .leading).padding(PresentationTokens.spacePage)
                            }
                        }.background(Color.suzentBackground)
                            .navigationTitle("Permissions").navigationBarTitleDisplayMode(.inline)
                    } label: { Text("Permissions") }.disabled(model.device == nil)
                    Toggle(isOn: Binding(get: { model.nodeEnabled }, set: { model.toggleNode($0) })) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Enable foreground Node")
                            if model.nodeEnabled {
                                Text(model.nodeStatus).font(.caption).foregroundStyle(Color.suzentMuted)
                            }
                        }
                    }.tint(Color(presentation: PresentationTokens.blue))
                    Button("Pair again") { model.beginPairing(repairActive: true); repairScanner = true }.disabled(model.busy || model.streaming)
                    Button("Forget this desktop", role: .destructive) { confirmForget = true }
                        .foregroundStyle(Color.suzentDanger).disabled(model.busy)
                } header: { settingsHeader("This desktop") } footer: {
                    Text("To revoke access, also remove its credentials on the desktop.").foregroundStyle(Color.suzentMuted)
                }
            }
            PreferencesSection(header: AnyView(settingsHeader("Preferences")))
            Section {
                if !model.isDemo {
                    Button("Try offline demo") { Task { await model.startDemo() } }.disabled(model.busy || model.streaming)
                }
                Link("Privacy policy", destination: suzentPrivacyPolicyURL)
            } header: { settingsHeader("About") }
        }
        .formStyle(.grouped)
        .alert("Forget this desktop?", isPresented: $confirmForget) {
            Button("Cancel", role: .cancel) {}
            Button("Forget", role: .destructive) { model.forget() }
        } message: { Text("This phone will need to pair again before it can reach your desktop.") }
    }

    private func activeDesktopLine(_ desktop: SavedDesktop) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "desktopcomputer").font(.system(size: 11, weight: .medium))
            Text(desktop.name).lineLimit(1).truncationMode(.tail)
        }.suzentFont(PresentationTokens.typeSidebarSection, weight: .semibold).foregroundStyle(Color.suzentMuted)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            .accessibilityLabel(Text("Desktop: \(desktop.name)"))
    }

    private func tabHeader(_ title: LocalizedStringKey) -> some View {
        Text(title).suzentFont(PresentationTokens.typeControl, weight: .bold)
            .frame(maxWidth: .infinity, minHeight: 44).padding(.top, 4).padding(.bottom, 4)
            .overlay(alignment: .bottom) { Rectangle().fill(Color.suzentText.opacity(0.08)).frame(height: 1) }
            .accessibilityAddTraits(.isHeader)
    }

    private var settingsTab: some View {
        VStack(spacing: 0) {
            tabHeader("Settings")
            settings.scrollContentBackground(.hidden)
        }.background(Color.suzentBackground)
    }

    private var tasksTab: some View {
        VStack(spacing: 0) {
            tabHeader("Tasks")
            List { taskRows(scope: "tasks") }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .environment(\.defaultMinListRowHeight, 0)
            .refreshable { await model.refresh() }
        }.background(Color.suzentSurface)
    }

    @ViewBuilder private func taskRows(scope: String) -> some View {
        let groups = scheduledSidebarGroups(model.chats, tasks: model.scheduledTasks, search: "", expanded: expandedAgents)
        if groups.isEmpty {
            Text("No scheduled tasks on \(model.activeDesktop?.name ?? model.origin)")
                .font(.subheadline).foregroundStyle(Color.suzentMuted).multilineTextAlignment(.center)
                .frame(maxWidth: .infinity).padding(.vertical, 40).sidebarListRow()
        }
        ForEach(groups) { group in
            if let task = group.task {
                scheduledTaskRow(task, root: group.root).sidebarListRow()
            } else if let root = group.root { conversationRows([root], scope: scope) }
            conversationRows(group.children, scope: scope, spacing: 0)
        }
    }

    private func settingsHeader(_ title: LocalizedStringKey) -> some View {
        Text(title).foregroundStyle(Color.suzentMuted)
    }

    private func conversation(_ chat: Chat) -> some View {
        let loadingHistory = model.openingChatID == chat.id && (chat.messages ?? []).isEmpty
        return GeometryReader { viewport in
        ZStack(alignment: .bottom) {
        VStack(spacing: 0) {
            if chat.isRegent {
                let sessions = Array(model.chats.filter { $0.parentChatId == chat.id }.prefix(5))
                if !sessions.isEmpty {
                    DisclosureGroup("Recent delegated conversations") {
                        ForEach(sessions) { session in
                            Button { Task { await model.open(session) } } label: {
                                HStack {
                                    Text(session.title).lineLimit(1)
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                }.suzentFont(PresentationTokens.typeCaption).frame(minHeight: 44)
                            }.buttonStyle(.plain).disabled(model.busy)
                        }
                    }.suzentFont(PresentationTokens.typeLabel).padding(.horizontal, 16).padding(.vertical, 8)
                }
            }
            FollowingChatScrollView(openedVersion: model.openedVersion, sentVersion: model.sentVersion,
                                   startsAtBottom: !chat.id.isEmpty, live: model.streaming || !model.liveParts.isEmpty, dismissKeyboard: { composing = false; attachmentsExpanded = false }) {
                    LazyVStack(alignment: .leading, spacing: PresentationTokens.spaceLarge) {
                        if chat.id.isEmpty { startPage(chat) }
                        let savedMessages = transcriptCache.content(chat.messages ?? [], liveToolIDs: Set(model.liveParts.filter { $0.type == "tool" }.compactMap(\.toolCallId)))
                        let messages = chat.isRegent ? regentMessages(savedMessages, liveParts: model.liveParts) : savedMessages
                        if loadingHistory { HistoryLoadingIndicator() }
                        if !loadingHistory && chat.isRegent && messages.isEmpty && !model.streaming { RegentGreeting() }
                        let hasLiveMessage = model.streaming || !model.liveParts.isEmpty
                        let idle = !model.busy && !hasLiveMessage && chat.isRunning != true
                        let lastUser = (chat.messages ?? []).lastIndex { $0.role == "user" }
                        let canReplay = !chat.isRegent && idle && !(chat.models ?? []).isEmpty && lastUser != nil && model.device?.permissions.send == true && model.device?.permissions.manageChats == true
                        ForEach(Array(messages.enumerated()), id: \.offset) { index, message in
                            MessageView(message: message, regent: chat.isRegent, isLatest: !hasLiveMessage && index == messages.count - 1, fallbackModel: chat.model,
                                canRetry: canReplay && (message.messageIndex == lastUser || (index == messages.count - 1 && message.role == "assistant")),
                                canEdit: canReplay && message.role == "user" && message.messageIndex == lastUser,
                                canFork: !chat.isRegent && idle && message.role == "assistant" && model.device?.permissions.createChats == true,
                                onAction: { action, text in Task { await model.messageAction(message, action: action, text: text) } })
                                .environment(\.railScope, railScope(chatId: chat.id, messageKey: "m\(message.messageIndex)"))
                        }
                        if hasLiveMessage {
                            VStack(alignment: .leading, spacing: 10) {
                                ActivityTurn(parts: chat.isRegent ? regentDisplayParts(model.liveParts, live: model.streaming) : model.liveParts,
                                             live: model.streaming, regent: chat.isRegent)
                            }
                            .environment(\.railScope, railScope(chatId: chat.id, messageKey: "live\(streamGeneration)"))
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(16).readingWidth()
                    .environment(\.surfaceHandler, surfaceHandler(chat))
            }.id(chat.id).environment(\.railChoices, railChoices)
            if !model.pendingApprovals.isEmpty {
                // Pinned above the composer so a pending decision never scrolls out of reach.
                ViewThatFits(in: .vertical) {
                    ApprovalCards(model: model)
                    ScrollView { ApprovalCards(model: model) }
                }.frame(maxHeight: viewport.size.height * 0.4)
                    .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 8).readingWidth()
            }
            toastHost(conversationVisible)
            composer(chat).readingWidth()
        }.frame(width: viewport.size.width, height: viewport.size.height)
            .offset(y: attachmentsExpanded ? -200 : 0)
        if !chat.isRegent { AttachmentPanel(model: model, expanded: $attachmentsExpanded)
            .frame(height: 200).offset(y: attachmentsExpanded ? 0 : 200)
            .allowsHitTesting(attachmentsExpanded).accessibilityHidden(!attachmentsExpanded) }
        }.clipped()
            .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: attachmentsExpanded)
        }.onChange(of: composing) { _, focused in if focused { attachmentsExpanded = false } }
            .onChange(of: chat.id) { _, _ in
                attachmentsExpanded = false
                railChoices.clear()
                let step = nextStreamGeneration(0, wasStreaming: false, streaming: model.streaming)
                streamGeneration = step.generation
                sawStreaming = step.streaming
            }
            .onChange(of: model.streaming, initial: true) { _, streaming in
                let step = nextStreamGeneration(streamGeneration, wasStreaming: sawStreaming, streaming: streaming)
                streamGeneration = step.generation
                sawStreaming = step.streaming
            }
            .task(id: "\(chat.id):\(model.openedVersion)") { await model.watchApprovals(chat.id) }
            .onDisappear { model.voice.stop() }
    }

    /// Question forms the user has replied to since, which are not offered again (desktop `isAnsweredQuestion`).
    private func answeredQuestions(_ chat: Chat) -> Set<String> {
        let messages = chat.messages ?? []
        guard let lastUser = messages.lastIndex(where: { $0.role == "user" }) else { return [] }
        return Set(messages.prefix(lastUser).flatMap(\.parts).compactMap { part -> String? in
            guard let surface = part.surface, case .form(_, _, "submit_question") = surface.component else { return nil }
            return surface.id
        })
    }

    private func surfaceHandler(_ chat: Chat) -> SurfaceHandler {
        let answered = answeredQuestions(chat)
        let idle = !model.busy && !model.streaming && chat.isRunning != true
        let canSend = model.device?.permissions.send == true && !chat.id.isEmpty
        return SurfaceHandler(
            // A blocked question is answered while the run waits; anything else starts a new turn.
            interactive: { surface in
                canSend && (surface.isDeferred ? model.surfacesSupported : idle && !answered.contains(surface.id))
            },
            act: { surface, action, context in await model.act(on: surface, action: action, context: context) })
    }

    private func composer(_ chat: Chat) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if model.voice.active {
                VoiceCubeView(voice: model.voice).frame(height: 112).accessibilityHidden(true)
                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(model.voice.status).suzentFont(14, weight: .medium)
                        if !model.voice.transcript.isEmpty {
                            Text(model.voice.transcript).suzentFont(14).lineLimit(3)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading)

                }.padding(.horizontal, 4)
            }
            PendingAttachmentStrip(model: model)
            HStack(alignment: .center) {
                if !chat.isRegent && model.attachmentsSupported && model.device?.permissions.send == true {
                    Button {
                        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
                            attachmentsExpanded.toggle()
                            if attachmentsExpanded { composing = false }
                        }
                    } label: {
                        Image(systemName: "plus").font(.system(size: 20)).frame(width: 44, height: 44)
                    }.buttonStyle(.plain).accessibilityLabel("Attach")
                        .disabled(model.busy || model.attachments.count >= maxAttachments)
                }
                TextField("Message", text: $model.draft, axis: .vertical).lineLimit(composing ? 1...6 : 1...1).focused($composing)
                    .tint(Color.suzentLink)
                    .suzentFont(PresentationTokens.typeChat).padding(.horizontal, 4).padding(.vertical, 12).frame(minHeight: 44).disabled(model.busy)
                Color.clear.frame(width: 44, height: 44)
            }
            if composing { HStack(spacing: 8) {
                Button {
                    composing = false; showModelPicker = true
                } label: {
                    HStack(spacing: 6) {
                        Text(model.selectedModel ?? chat.model ?? String(localized: "Desktop model")).lineLimit(1).truncationMode(.middle)
                        Image(systemName: "chevron.down").font(.system(size: 10, weight: .semibold))
                    }.suzentFont(PresentationTokens.typeLabel, weight: .medium).foregroundStyle(Color.suzentMuted).frame(minHeight: 44)
                }.buttonStyle(.plain)
                .disabled(model.busy || model.streaming || (chat.models ?? []).isEmpty || model.device?.permissions.send != true)
                Spacer(minLength: 8)
                Color.clear.frame(width: 44, height: 44)
            }.transition(.opacity) }
        }.padding(10).background(Color.suzentSurface)
            .dynamicTypeSize(...DynamicTypeSize.accessibility3)
            .animation(reduceMotion ? nil : .smooth(duration: 0.28, extraBounce: 0), value: composing)
            .overlay(alignment: .bottomTrailing) { sendAction(chat).padding(10) }
            .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
            .background { Rectangle().fill(Color.suzentShadow).offset(x: 2, y: 2) }
            .padding(.trailing, 2).padding(.bottom, 2)
            .padding(.horizontal, 12).padding(.bottom, 8)
    }

    private func startPage(_ chat: Chat) -> some View {
        VStack(spacing: 28) {
            GreetingCube(engaged: keyboardVisible).frame(width: keyboardVisible ? 90 : 160, height: keyboardVisible ? 90 : 160)
            TimelineView(.periodic(from: .now, by: 60)) { context in
                let hour = Calendar.current.component(.hour, from: context.date)
                let greeting: LocalizedStringKey = hour < 5 ? "Night owl?" : hour < 12 ? "Good morning." : hour < 17 ? "Keep building." : hour < 21 ? "Good evening." : "Bed time? Or maybe late night coding?"
                Text(greeting).textCase(.uppercase).suzentFont(30, weight: .black)
                    .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }
            SuzentSelectionTrigger(value: chat.projectName ?? String(localized: "Home"), prefix: String(localized: "Creating in")) {
                composing = false; showProjectPicker = true
            }.disabled(model.busy || model.projects.isEmpty)
            if model.isDemo {
                ForEach(model.demoPrompts, id: \.self) { prompt in
                    Button(prompt) { model.draft = prompt; sends += 1; Task { await model.send() } }
                        .buttonStyle(SuzentButtonStyle()).disabled(model.busy || model.streaming)
                }
            }
        }.frame(maxWidth: .infinity).padding(.horizontal, 8).padding(.vertical, keyboardVisible ? 12 : 40)
    }

    private func sendAction(_ chat: Chat) -> some View {
        let action = ComposerAction.resolve(
            hasContent: !model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !model.attachments.isEmpty,
            busy: model.busy, running: model.streaming || chat.isRunning == true,
            voiceActive: model.voice.active, voiceConnecting: model.voice.animationState == "connecting")
        let loading = action == .loading || (action == .stop && model.stopInFlight)
        let label: String = switch action {
        case .voice: String(localized: "Start voice conversation")
        case .send: String(localized: "Send")
        case .loading: String(localized: "Processing…")
        case .connecting: String(localized: "Cancel voice connection")
        case .hangUp: String(localized: "End voice conversation")
        case .stop: model.stopInFlight ? String(localized: "Stopping…") : String(localized: "Stop")
        }
        let symbol = action == .stop ? "stop.fill" : action == .hangUp ? "phone.down.fill" : action == .voice ? "waveform" : "arrow.up"
        return Button {
            switch action {
            case .voice: composing = false; model.startVoice()
            case .hangUp, .connecting: model.voice.stop()
            case .loading: break
            case .stop:
                guard model.device?.permissions.stop == true else {
                    model.error = String(localized: "Change this phone’s permissions in desktop Settings → Devices to use this action."); return
                }
                Task { await model.stop() }
            case .send:
                guard model.device?.permissions.send == true else {
                    model.error = String(localized: "Change this phone’s permissions in desktop Settings → Devices to use this action."); return
                }
                guard !chat.id.isEmpty || model.device?.permissions.createChats == true else {
                    model.error = String(localized: "Enable Create conversations for this phone, or open an existing conversation."); return
                }
                sends += 1
                Task { await model.send() }
            }
        } label: {
            Group {
                if loading || action == .connecting { ProgressView().tint(.white) }
                else { Image(systemName: symbol).font(.system(size: action == .stop ? 14 : 20, weight: .bold)) }
            }.foregroundStyle(.white).frame(width: 36, height: 36)
                .background(Color(presentation: action == .stop || action == .hangUp ? PresentationTokens.danger : PresentationTokens.blue))
                .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 2))
                .padding(4).contentShape(Rectangle())
        }.buttonStyle(.plain).disabled(loading).accessibilityLabel(label)
    }

}

private extension View {
    /// Keeps lines readable when the conversation fills a wide iPad column.
    func readingWidth() -> some View { frame(maxWidth: 760).frame(maxWidth: .infinity) }
}

/// Owns its focus: focus state held by the root view does not reach a pushed navigation destination.
private struct SearchPageField: View {
    @Binding var text: String
    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundStyle(Color.suzentMuted)
            TextField("Search chats", text: $text).suzentFont(16)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
                .submitLabel(.search).focused($focused)
            if !text.isEmpty {
                Button { text = ""; focused = true } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(Color.suzentMuted)
                }.buttonStyle(.plain).frame(minWidth: 32, minHeight: 42).accessibilityLabel("Clear search")
            }
        }.padding(.horizontal, 12).frame(minHeight: 42)
            .background(Color.suzentText.opacity(0.04))
            // Only on the way in: coming back from a result should not raise the keyboard again. Focus set
            // during the push transition is dropped, so it waits for the page to settle.
            .task {
                guard text.isEmpty else { return }
                try? await Task.sleep(for: .milliseconds(450))
                focused = true
            }
    }
}

private struct HistoryLoadingIndicator: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible = false

    var body: some View {
        ProgressView().tint(Color.suzentMuted)
            .opacity(visible ? 1 : 0)
            .frame(maxWidth: .infinity, minHeight: 68)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.14), value: visible)
            .accessibilityHidden(!visible)
            .task {
                try? await Task.sleep(for: .milliseconds(180))
                guard !Task.isCancelled else { return }
                visible = true
            }
    }
}
