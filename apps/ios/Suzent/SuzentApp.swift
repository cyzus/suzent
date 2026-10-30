import SwiftUI
import SuzentCore
import MarkdownUI

@main struct SuzentApp: App {
    @State private var model = MobileModel()
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            ContentView(model: model)
                .onChange(of: phase) { _, phase in
                    Task { await model.setForeground(phase == .active) }
                }
        }
    }
}

private enum Route: Hashable { case conversation, settings }

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
                    Button { manage(pinned ? "unpin" : "pin", nil) } label: {
                        Label(pinned ? LocalizedStringKey("Unpin") : LocalizedStringKey("Pin"), systemImage: pinned ? "pin.slash" : "pin")
                    }.tint(Color(presentation: PresentationTokens.blue))
                }
            }
            .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                if swipeable {
                    // Not role: .destructive, which would animate the row away before the confirmation.
                    Button { deleting = true } label: { Label("Delete", systemImage: "trash") }
                        .tint(Color.suzentDanger)
                }
            }
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
    @State private var expandedProject: String? = nil
    @State private var showAllScheduled = false
    @State private var scheduledExpanded = false
    @State private var showAllRecent = false
    @State private var expandedAgents: Set<String> = []
    @State private var regentPressed = false
    @FocusState private var composing: Bool
    @State private var keyboardVisible = false
    @State private var attachmentsExpanded = false
    @State private var showModelPicker = false
    @State private var showProjectPicker = false
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
                NavigationSplitView(columnVisibility: .constant(.all)) {
                    sidebar(home: false)
                        .navigationSplitViewColumnWidth(PresentationTokens.sidebarWidth)
                        .toolbar(removing: .sidebarToggle)
                        .overlay(alignment: .trailing) {
                            Rectangle().fill(Color.suzentShadow).frame(width: PresentationTokens.borderWidthHeavy)
                                .ignoresSafeArea().accessibilityHidden(true)
                        }
                } detail: {
                    NavigationStack { detail }
                }.navigationSplitViewStyle(.balanced)
            } else {
                NavigationStack(path: $path) {
                    sidebar(home: true)
                        .navigationDestination(for: Route.self) { route in
                            switch route {
                            case .conversation: detail
                            case .settings: settingsPage
                            }
                        }
                }
            }
        }
        .background(Color.suzentBackground)
        .foregroundStyle(Color.suzentText)
        .overlay(alignment: .bottom) { toastHost(!conversationVisible) }
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
            if !path.contains(.settings) { showSettings = false }
            if path.isEmpty { composing = false; attachmentsExpanded = false }
        }
        .onChange(of: model.selected == nil) { _, missing in
            if missing && path.last == .conversation { path = [] }
        }
        .onChange(of: wide) { _, wide in
            if !wide { path = showSettings ? [.settings] : model.selected != nil ? [.conversation] : [] }
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
        .sensoryFeedback(.impact(weight: .light), trigger: sends)
        .onChange(of: model.isDemo) { _, _ in
            showSettings = false; path = []; showModelPicker = false; showProjectPicker = false; composing = false
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
        if !wide && path != [.conversation] { path = [.conversation] }
    }

    private func openSettings() {
        composing = false
        showSettings = true
        if !wide { path = [.settings] }
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
                        ReconnectIndicator(active: model.busy)
                        Text(model.busy ? String(localized: "Connecting to Suzent") : String(localized: "Reconnect to desktop"))
                            .suzentFont(21, weight: .medium).multilineTextAlignment(.center)
                        Group {
                            if model.busy {
                                if model.reconnecting { Button("Cancel") { model.cancelReconnect() } }
                            } else { Button("Reconnect to desktop") { Task { await model.connect() } } }
                        }.suzentFont(PresentationTokens.typeCaption).foregroundStyle(Color.suzentMuted)
                            .buttonStyle(.plain).frame(minHeight: 44)
                    }
                    Spacer(minLength: 20)
                    Button("Connection help") { showConnectionHelp = true }
                        .suzentFont(PresentationTokens.typeLabel).foregroundStyle(Color.suzentMuted)
                        .frame(minHeight: 44).buttonStyle(.plain)
                }.padding(.horizontal, 24).padding(.bottom, 20)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .confirmationDialog("Connection help", isPresented: $showConnectionHelp, titleVisibility: .visible) {
                        Button("Pair again") { model.error = nil; repairScanner = true }.disabled(model.busy || model.streaming)
                        Button("Forget connection", role: .destructive) { model.forget() }.disabled(model.busy)
                        Button("Cancel", role: .cancel) { }
                    } message: { Text("Check that Suzent is running on your desktop and both devices are online.") }
            } else {
                Rectangle().fill(Color.suzentOutline).frame(height: PresentationTokens.borderWidth)
                PairingView(model: model)
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity).background(Color.suzentBackground)
    }

    @ViewBuilder private var demoBanner: some View {
        if model.isDemo {
            HStack {
                Text("Offline demo · Scripted replies, no AI calls").font(.footnote)
                Spacer()
                Button("Exit demo") { model.exitDemo() }.font(.footnote.bold()).buttonStyle(.plain)
                    .frame(minHeight: 44).disabled(model.busy)
            }.padding(.horizontal, 16)
                .background(Color(presentation: PresentationTokens.yellow), ignoresSafeAreaEdges: []).foregroundStyle(.black)
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
        .safeAreaInset(edge: .top, spacing: 0) { demoBanner }
        .navigationBarTitleDisplayMode(.inline)
        .toolbarRole(.editor)
        .toolbar {
            if !showSettings {
                ToolbarItem(placement: .principal) { conversationTitle.dynamicTypeSize(...DynamicTypeSize.accessibility3) }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: newConversation) { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("New conversation")
                        .disabled(model.busy || model.device?.permissions.createChats != true)
                }
            }
        }
    }

    private var settingsPage: some View {
        settings.navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
            .safeAreaInset(edge: .top, spacing: 0) { demoBanner }
            .toolbarRole(.editor)
    }

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
        } else { SuzentWordmark() }
    }

    private func sidebar(home: Bool) -> some View {
        let searchQuery = ChatPageQuery("search", value: search.trimmingCharacters(in: .whitespacesAndNewlines))
        let recentRows = sidebarChats(model.pageChats(ChatPageQuery()), search: "", expanded: expandedAgents)
        let pinnedRows = sidebarChats(model.pageChats(ChatPageQuery("pinned")), search: "", expanded: expandedAgents)
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                if home {
                    SuzentWordmark()
                } else {
                    SuzentLogoMark().frame(width: 24, height: 24)
                    Text("SUZENT").tracking(2).suzentFont(14, weight: .bold)
                }
                Spacer()
                Button(action: openSettings) {
                    Image(systemName: "gearshape").font(.system(size: 20)).frame(width: 44, height: 44)
                }.buttonStyle(.plain).accessibilityLabel("Settings")
            }.padding(.horizontal, 20).padding(.top, 4).padding(.bottom, 4)
                .dynamicTypeSize(...DynamicTypeSize.accessibility3)
            if home { demoBanner }
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
            Button(action: newConversation) {
                Label("New conversation", systemImage: "square.and.pencil")
                    .suzentFont(home ? 16 : PresentationTokens.typeCaption, weight: .semibold)
                    .foregroundStyle(Color.black)
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .padding(.horizontal, 12)
                    .background(Color(presentation: PresentationTokens.yellow))
            }.buttonStyle(.plain)
                .disabled(model.busy || model.device?.permissions.createChats != true)
                .padding(.horizontal, 16).padding(.top, 12)
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(Color.suzentMuted)
                TextField("Search chats", text: $search).suzentFont(home ? 16 : 14)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
            }.padding(.horizontal, 12).frame(minHeight: 42)
                .background(Color.suzentText.opacity(0.04))
                .padding(.horizontal, 16).padding(.vertical, 12)
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
                        if !pinnedRows.isEmpty {
                            sidebarHeading("Pinned").sidebarListRow()
                            conversationRows(pinnedRows, scope: "pinned")
                            pageFooter(ChatPageQuery("pinned"))
                        }
                        let recent = recentRows.filter { $0.depth == 0 }
                        if !recent.isEmpty {
                            HStack {
                                sidebarHeading("Recent")
                                Spacer()
                                if (model.chatPages[ChatPageQuery()]?.total ?? 0) > 3 {
                                    Button(showAllRecent ? "Show fewer" : "View all") { showAllRecent.toggle() }
                                        .font(.caption).foregroundStyle(Color.suzentMuted).frame(minHeight: 44).buttonStyle(.plain)
                                }
                            }.sidebarListRow()
                            let recentIDs = Set((showAllRecent ? recent : Array(recent.prefix(3))).map { $0.chat.id })
                            conversationRows(recentRows.filter { recentIDs.contains($0.root.id) }, scope: "recent")
                        }
                        if showAllRecent { pageFooter(ChatPageQuery()) }
                        if !projects.isEmpty { sidebarHeading("Projects").sidebarListRow() }
                        ForEach(projects) { project in projectSection(project) }
                        if pinnedRows.isEmpty && recentRows.isEmpty {
                            Text("No chats yet").font(.subheadline).foregroundStyle(Color.suzentMuted).padding(.vertical, 24).sidebarListRow()
                        }
                    }
                    scheduledSection
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

    @ViewBuilder private var scheduledSection: some View {
        let groups = scheduledSidebarGroups(model.chats, tasks: model.scheduledTasks, search: search, expanded: expandedAgents)
        // Matches the desktop automation preview: five rows, then View all.
        let previewLimit = 5
        let visible = showAllScheduled || !search.isEmpty ? groups : Array(groups.prefix(previewLimit))
        if !groups.isEmpty {
            Button { withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { scheduledExpanded.toggle() } } label: {
                HStack(spacing: 10) {
                    Image(systemName: "clock")
                    Text("Scheduled tasks")
                    Spacer()
                    Text("\(groups.count)").font(.caption).foregroundStyle(Color.suzentMuted)
                    Image(systemName: scheduledExpanded || !search.isEmpty ? "chevron.down" : "chevron.right").font(.caption)
                }.suzentFont(14, weight: .medium).frame(minHeight: 48).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityValue(scheduledExpanded ? Text("Expanded") : Text("Collapsed"))
                .sidebarListRow()
            ForEach(scheduledExpanded || !search.isEmpty ? visible : []) { group in
                if let task = group.task {
                    scheduledTaskRow(task, root: group.root).sidebarListRow()
                } else if let root = group.root { conversationRows([root], scope: "scheduled") }
                conversationRows(group.children, scope: "scheduled", spacing: 0)
            }
            if scheduledExpanded && search.isEmpty && groups.count > previewLimit {
                Button { showAllScheduled.toggle() } label: {
                    Text(showAllScheduled ? "Show fewer" : "View all \(groups.count) scheduled tasks")
                        .suzentFont(PresentationTokens.typeCaption, weight: .bold)
                        .frame(maxWidth: .infinity, minHeight: PresentationTokens.controlHeight)
                }.buttonStyle(.plain).sidebarListRow()
            }
        }
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
                Section {
                    NavigationLink {
                        ScrollView {
                            if let device = model.device {
                                ClientPermissionsView(device: device, origin: model.origin)
                                    .frame(maxWidth: .infinity, alignment: .leading).padding(PresentationTokens.spacePage)
                            }
                        }.background(Color.suzentBackground)
                            .navigationTitle("Desktop access").navigationBarTitleDisplayMode(.inline)
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(model.device?.displayName ?? String(localized: "Desktop access"))
                            Text(model.origin).font(.caption.monospaced()).foregroundStyle(Color.suzentMuted).lineLimit(1)
                        }
                    }.disabled(model.device == nil)
                } header: { settingsHeader("Desktop access") }
                Section {
                    Toggle("Enable foreground Node", isOn: Binding(get: { model.nodeEnabled }, set: { model.toggleNode($0) }))
                        .tint(Color(presentation: PresentationTokens.blue))
                } header: { settingsHeader("This phone as a Node") } footer: {
                    Text(model.nodeStatus).foregroundStyle(Color.suzentMuted)
                }
                Section {
                    Button("Pair again") { model.error = nil; repairScanner = true }.disabled(model.busy || model.streaming)
                    Button("Forget connection", role: .destructive) { confirmForget = true }
                        .foregroundStyle(Color.suzentDanger).disabled(model.busy)
                } header: { settingsHeader("Connection") } footer: {
                    Text("To revoke access, also remove its credentials on the desktop.").foregroundStyle(Color.suzentMuted)
                }
                Section {
                    Button("Try offline demo") { Task { await model.startDemo() } }.disabled(model.busy || model.streaming)
                } header: { settingsHeader("About") }
            }
        }
        .formStyle(.grouped)
        .alert("Forget connection?", isPresented: $confirmForget) {
            Button("Cancel", role: .cancel) {}
            Button("Forget connection", role: .destructive) { model.forget() }
        } message: { Text("This phone will need to pair again before it can reach your desktop.") }
    }

    private func settingsHeader(_ title: LocalizedStringKey) -> some View {
        Text(title).foregroundStyle(Color.suzentMuted)
    }

    private func conversation(_ chat: Chat) -> some View {
        GeometryReader { viewport in
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
                        if chat.isRegent && messages.isEmpty && !model.streaming { RegentGreeting() }
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
                        }
                        if hasLiveMessage {
                            VStack(alignment: .leading, spacing: 10) {
                                ActivityTurn(parts: chat.isRegent ? regentDisplayParts(model.liveParts, live: model.streaming) : model.liveParts,
                                             live: model.streaming, regent: chat.isRegent)
                            }
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(16)
            }.id(chat.id)
            if !model.pendingApprovals.isEmpty {
                // Pinned above the composer so a pending decision never scrolls out of reach.
                ViewThatFits(in: .vertical) {
                    ApprovalCards(model: model)
                    ScrollView { ApprovalCards(model: model) }
                }.frame(maxHeight: viewport.size.height * 0.4)
                    .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 8)
            }
            toastHost(conversationVisible)
            composer(chat)
        }.frame(width: viewport.size.width, height: viewport.size.height)
            .offset(y: attachmentsExpanded ? -200 : 0)
        if !chat.isRegent { AttachmentPanel(model: model, expanded: $attachmentsExpanded)
            .frame(height: 200).offset(y: attachmentsExpanded ? 0 : 200)
            .allowsHitTesting(attachmentsExpanded).accessibilityHidden(!attachmentsExpanded) }
        }.clipped()
            .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: attachmentsExpanded)
        }.onChange(of: composing) { _, focused in if focused { attachmentsExpanded = false } }
            .onChange(of: chat.id) { _, _ in attachmentsExpanded = false }
            .task(id: "\(chat.id):\(model.openedVersion)") { await model.watchApprovals(chat.id) }
    }

    private func composer(_ chat: Chat) -> some View {
        VStack(alignment: .leading, spacing: 8) {
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
                if !composing { sendAction(chat) } else { Color.clear.frame(width: 44, height: 44) }
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
                sendAction(chat)
            } }
        }.padding(10).background(Color.suzentSurface)
            .dynamicTypeSize(...DynamicTypeSize.accessibility3)
            .animation(reduceMotion ? nil : .easeInOut(duration: 0.18), value: composing)
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
            SuzentSelectionTrigger(value: chat.projectName ?? "Home", prefix: String(localized: "Creating in")) {
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
        let stopping = model.streaming || chat.isRunning == true
        let enabled = stopping ? model.device?.permissions.stop == true :
            !model.busy && model.device?.permissions.send == true &&
            (!model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !model.attachments.isEmpty)
        return Button {
            if !stopping { sends += 1 }
            Task { if stopping { await model.stop() } else { await model.send() } }
        } label: {
            Image(systemName: stopping ? "stop.fill" : "arrow.up")
                .font(.system(size: stopping ? 14 : 20, weight: .bold)).foregroundStyle(.white)
                .frame(width: 36, height: 36)
                .background(stopping ? Color.suzentDanger : Color.suzentLink)
                .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 2))
                .padding(4).contentShape(Rectangle())
        }.buttonStyle(.plain).disabled(!enabled).opacity(enabled ? 1 : PresentationTokens.disabledAlpha)
            .accessibilityLabel(stopping ? String(localized: "Stop") : String(localized: "Send"))
    }

}
