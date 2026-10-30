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

private struct ChatMenuPresentation {
    let anchor: Anchor<CGRect>
    let content: AnyView
    let preferredHeight: CGFloat
    let dismiss: () -> Void
}

private struct ChatMenuPreferenceKey: PreferenceKey {
    static var defaultValue: [ChatMenuPresentation] { [] }
    static func reduce(value: inout [ChatMenuPresentation], nextValue: () -> [ChatMenuPresentation]) {
        value.append(contentsOf: nextValue())
    }
}

private struct SidebarFoldAnchorKey: PreferenceKey {
    static var defaultValue: Anchor<CGRect>? { nil }
    static func reduce(value: inout Anchor<CGRect>?, nextValue: () -> Anchor<CGRect>?) {
        value = value ?? nextValue()
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
            }.font(.system(size: PresentationTokens.typeSidebarSection, weight: .medium)).foregroundStyle(Color.suzentMuted)
                .padding(.horizontal, 4)
                .frame(minHeight: 16).contentShape(Rectangle())
        }.buttonStyle(.plain)
            .accessibilityLabel(expanded ? Text("Collapse sub-agents: \(count)") : Text("Expand sub-agents: \(count)"))
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
    @State private var menu = false
    @State private var moving = false
    @State private var renaming = false
    @State private var deleting = false
    @State private var title = ""

    private var meta: Text? {
        if chat.isSubagent && !nested { return parentTitle.map { Text("Sub-agent of \($0)") } ?? Text("Sub-agent") }
        if chat.isScheduled { return Text("Scheduled task") }
        return chat.projectName.map { Text($0) }
    }

    var body: some View {
        Button { if !menu { open() } } label: {
            HStack(spacing: 6) {
                if chat.pinned == true { Image(systemName: "pin.fill").font(.system(size: 10)) }
                VStack(alignment: .leading, spacing: 0) {
                    Text(chat.title).font(.system(size: PresentationTokens.typeCaption, weight: .medium))
                        .lineLimit(1).truncationMode(.tail)
                    HStack(spacing: 0) {
                        if let meta { meta.lineLimit(1).truncationMode(.tail) }
                        if meta != nil && childCount > 0 { Text(" · ") }
                        if childCount > 0 {
                            SidebarFoldControl(count: childCount, expanded: childrenExpanded, toggle: {}).hidden()
                                .anchorPreference(key: SidebarFoldAnchorKey.self, value: .bounds) { $0 }
                        }
                    }.font(.system(size: PresentationTokens.typeSidebarSection, weight: .medium))
                        .foregroundStyle(Color.suzentMuted)
                        .frame(height: meta != nil || childCount > 0 ? 16 : 0)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Spacer(minLength: 0)
                if chat.isRunning == true { Image(systemName: "ellipsis") }
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
            .simultaneousGesture(LongPressGesture().onEnded { _ in
                guard enabled else { return }
                moving = false; menu = true
            })
            .accessibilityAction(named: Text("Conversation actions")) { moving = false; menu = true }
            .anchorPreference(key: ChatMenuPreferenceKey.self, value: .bounds) { anchor in
                menu ? [ChatMenuPresentation(anchor: anchor, content: AnyView(menuPanel), preferredHeight: !canManage ? 120 : moving ? 305 : 178, dismiss: { menu = false })] : []
            }
            .alert("Rename", isPresented: $renaming) {
                TextField("Conversation title", text: $title)
                Button("Cancel", role: .cancel) {}
                Button("Save") { manage("rename", title.trimmingCharacters(in: .whitespacesAndNewlines)) }
                    .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || title.count > 200)
            }
            .alert("Delete conversation?", isPresented: $deleting) {
                Button("Cancel", role: .cancel) {}
                Button("Delete", role: .destructive) { manage("delete", nil) }
            } message: { Text("This deletes the conversation on all devices and cannot be undone.") }
    }

    private var menuPanel: some View {
        VStack(spacing: 0) {
            if !canManage {
                Text("Enable Manage conversations in desktop Settings → Mobile access.")
                    .font(.footnote).padding(16)
            } else if moving {
                menuItem("Move to project", icon: "chevron.left") { moving = false }
                Divider()
                ScrollView {
                    VStack(spacing: 0) {
                        ForEach(projects) { project in
                            Button { menu = false; manage("move", project.id) } label: {
                                HStack { Text(project.name); Spacer(); if project.id == chat.projectId { Image(systemName: "checkmark") } }
                                    .padding(12).frame(minHeight: 44)
                            }.buttonStyle(ChatRowButtonStyle(selected: false)).disabled(project.id == chat.projectId)
                        }
                    }
                }.frame(maxHeight: 260)
            } else {
                menuItem(chat.pinned == true ? "Unpin" : "Pin", icon: "pin") { menu = false; manage(chat.pinned == true ? "unpin" : "pin", nil) }
                menuItem("Rename", icon: "pencil") { menu = false; title = chat.title; renaming = true }
                menuItem("Move to project", icon: "folder") { moving = true }
                    .disabled(chat.isRunning == true || projects.isEmpty)
                Divider()
                menuItem("Delete conversation", icon: "trash", danger: true) { menu = false; deleting = true }
                    .disabled(chat.isRunning == true)
            }
        }.frame(width: 260).background(Color.suzentSurface)
            .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
            .background {
                Rectangle().fill(Color.black).offset(x: PresentationTokens.shadowOffsetOverlay, y: PresentationTokens.shadowOffsetOverlay)
                    .allowsHitTesting(false).accessibilityHidden(true)
            }
    }

    private func menuItem(_ title: LocalizedStringKey, icon: String, danger: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: icon).font(.system(size: 13, weight: .bold))
                .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 12).frame(minHeight: 44)
        }.buttonStyle(ChatRowButtonStyle(selected: false, destructive: danger))
    }
}

struct ContentView: View {
    @Bindable var model: MobileModel
    @State private var showSidebar = true
    @State private var transcriptCache = ChatPresentationCache()
    @State private var showSettings = false
    @State private var repairScanner = false
    @State private var showConnectionHelp = false
    @State private var search = ""
    @State private var expandedProject: String? = nil
    @State private var showAllScheduled = false
    @State private var scheduledExpanded = false
    @State private var showAllRecent = false
    @State private var expandedAgents: Set<String> = []
    @FocusState private var composing: Bool
    @State private var keyboardVisible = false
    @State private var attachmentsExpanded = false
    @State private var showModelPicker = false
    @State private var showProjectPicker = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

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
        // The backend lists chats newest-first (updated_at desc), so a project's earliest
        // chat index is its latest activity. Mirrors the desktop sidebar's sortedProjects
        // ordering without adding a timestamp to the mobile payload.
        var activity: [String: Int] = [:]
        for (index, chat) in model.chats.enumerated() {
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
        GeometryReader { geometry in
            let wide = geometry.size.width >= 760
            ZStack(alignment: .leading) {
                HStack(spacing: 0) {
                    if wide && model.connected {
                        sidebar(home: false).frame(width: PresentationTokens.sidebarWidth)
                        Rectangle().fill(Color.suzentShadow).frame(width: PresentationTokens.borderWidthHeavy)
                            .ignoresSafeArea(edges: .bottom)
                    }
                    VStack(spacing: 0) {
                        HStack {
                            if model.connected && !wide {
                                Button { composing = false; withAnimation { showSidebar = true } } label: {
                                    Image(systemName: "chevron.left")
                                }.buttonStyle(SuzentIconButtonStyle()).accessibilityLabel("Back to chats")
                            }
                            Group {
                                if model.connected && showSettings {
                                    Text("Settings").font(.headline).lineLimit(1)
                                } else if model.connected, let chat = model.selected, !chat.id.isEmpty {
                                    if chat.isRegent {
                                        RegentIdentity(working: model.streaming || chat.isRunning == true, waiting: chat.regent?.waiting ?? 0)
                                    } else {
                                    VStack(spacing: 2) {
                                        if let project = chat.projectName {
                                            Text(project).font(.caption).foregroundStyle(Color.suzentMuted).lineLimit(1)
                                        }
                                        Text(chat.title).font(.system(size: PresentationTokens.typeControl, weight: .semibold))
                                            .lineLimit(1).truncationMode(.tail)
                                    }.padding(.horizontal, 8).multilineTextAlignment(.center)
                                    }
                                } else if !model.connected && model.canReconnect {
                                    Text("SUZENT").font(.system(size: 13, weight: .semibold)).tracking(2)
                                        .foregroundStyle(Color.suzentMuted).frame(maxWidth: .infinity, alignment: .leading)
                                } else { SuzentWordmark() }
                            }.frame(maxWidth: .infinity, minHeight: PresentationTokens.controlHeight)
                            if model.connected {
                                Button { composing = false; Task { await model.createChat(); showSettings = false; showSidebar = false } } label: {
                                    Image(systemName: "square.and.pencil")
                                }.buttonStyle(SuzentIconButtonStyle()).accessibilityLabel("New conversation")
                                    .disabled(model.busy || model.device?.permissions.createChats != true)
                            }
                        }.padding(.horizontal, 12).padding(.vertical, 6)
                        if model.connected || !model.canReconnect { Rectangle().fill(Color.suzentOutline).frame(height: PresentationTokens.borderWidth) }
                        if model.isDemo {
                            HStack {
                                Text("Offline demo · Scripted replies, no AI calls").font(.footnote)
                                Spacer()
                                Button("Exit demo") { model.exitDemo() }.font(.footnote.bold()).disabled(model.busy)
                            }.padding(.horizontal, 16).padding(.vertical, 8)
                                .background(Color(presentation: PresentationTokens.yellow)).foregroundStyle(.black)
                        }
                        if let error = model.error {
                            SuzentNotice(message: error) { model.error = nil }
                        }
                        if !model.connected && model.canReconnect {
                            VStack {
                                Spacer(minLength: 20)
                                VStack(spacing: 21) {
                                    ReconnectIndicator(active: model.busy)
                                    Text(model.busy ? String(localized: "Connecting to Suzent") : String(localized: "Reconnect to desktop"))
                                        .font(.system(size: 21, weight: .medium)).multilineTextAlignment(.center)
                                    Group {
                                        if model.busy {
                                            if model.reconnecting { Button("Cancel") { model.cancelReconnect() } }
                                        } else { Button("Reconnect to desktop") { Task { await model.connect() } } }
                                    }.font(.system(size: 13)).foregroundStyle(Color.suzentMuted)
                                        .buttonStyle(.plain).frame(minHeight: 44)
                                }
                                Spacer(minLength: 20)
                                Button("Connection help") { showConnectionHelp = true }
                                    .font(.system(size: 12)).foregroundStyle(Color.suzentMuted)
                                    .frame(minHeight: 44).buttonStyle(.plain)
                            }.padding(.horizontal, 24).padding(.bottom, 20)
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                                .confirmationDialog("Connection help", isPresented: $showConnectionHelp, titleVisibility: .visible) {
                                    Button("Pair again") { model.error = nil; repairScanner = true }.disabled(model.busy || model.streaming)
                                    Button("Forget connection", role: .destructive) { model.forget() }.disabled(model.busy)
                                    Button("Cancel", role: .cancel) { }
                                } message: { Text("Check that Suzent is running on your desktop and both devices are online.") }

                        }
                        else if !model.connected { PairingView(model: model) }
                        else if showSettings { settings }
                        else if let chat = model.selected { conversation(chat) }
                        else {
                            if model.busy { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
                            else { Text("Select a conversation or start a new one.").foregroundStyle(Color.suzentMuted).padding().frame(maxWidth: .infinity, maxHeight: .infinity) }
                        }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                .accessibilityHidden(!wide && model.connected && showSidebar)
                if !wide && model.connected {
                    sidebar(home: true)
                        .frame(width: geometry.size.width, height: geometry.size.height)
                        .background(Color.suzentSurface)
                        .offset(x: showSidebar ? 0 : -geometry.size.width)
                        .allowsHitTesting(showSidebar)
                        .accessibilityHidden(!showSidebar)
                }
            }.background(Color.suzentBackground).clipped()
                .onChange(of: model.selected?.isRegent == true && !showSettings && (wide || !showSidebar), initial: true) { _, visible in
                    model.regentVisible = visible
                }
                .foregroundStyle(Color.suzentText)
                .overlayPreferenceValue(ChatMenuPreferenceKey.self) { menus in
                    GeometryReader { proxy in
                        if let menu = menus.last {
                            let row = proxy[menu.anchor]
                            let height = min(menu.preferredHeight, proxy.size.height - 32)
                            let top = row.maxY + 4 + height <= proxy.size.height - 16 ? row.maxY + 4 : max(16, row.minY - height - 4)
                            ZStack(alignment: .topLeading) {
                                Color.black.opacity(0.001).ignoresSafeArea()
                                    .onTapGesture { menu.dismiss() }.accessibilityHidden(true)
                                menu.content.frame(maxHeight: height, alignment: .top)
                                    .offset(x: max(16, min(row.minX, proxy.size.width - 276)), y: top)
                            }.accessibilityAddTraits(.isModal)
                                .accessibilityAction(.escape) { menu.dismiss() }
                        }
                    }
                }
        }
        .task { if model.canReconnect && !model.connected { await model.connect() } }
        .tint(Color.suzentText)
        .task(id: model.connected) { if model.connected { await model.watchNavigation() } }
        .onChange(of: model.connected) { _, connected in showModelPicker = false; showProjectPicker = false; showSidebar = true; if !connected { showSettings = false } }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in keyboardVisible = true }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in keyboardVisible = false }
        .accessibilityHidden(showModelPicker || showProjectPicker)
        .overlay { selectionOverlay }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: showModelPicker || showProjectPicker)
        .onChange(of: model.isDemo) { _, _ in
            showSettings = false; showSidebar = true; showModelPicker = false; showProjectPicker = false; composing = false
        }
        .onChange(of: model.sentVersion) { _, _ in composing = false }
        .fullScreenCover(isPresented: $repairScanner) { PairingScanner(model: model) }
    }

    private var selectionOverlay: some View {
            GeometryReader { geometry in
                if showModelPicker || showProjectPicker {
                    ZStack(alignment: .bottom) {
                        Color.black.opacity(0.32).ignoresSafeArea()
                            .onTapGesture { dismissSelection() }.accessibilityHidden(true)
                        Group {
                            if showModelPicker {
                                SuzentSelectionPanel(title: String(localized: "Desktop model"),
                                    options: [(id: "", title: String(localized: "Conversation default"))] + Array(Set(model.selected?.models ?? [])).sorted().map { (id: $0, title: $0) },
                                    selected: model.selectedModel ?? "", dismiss: dismissSelection) {
                                        model.selectModel($0.isEmpty ? nil : $0)
                                    }
                            } else {
                                SuzentSelectionPanel(title: String(localized: "Creating in"),
                                    options: model.projects.map { (id: $0.id, title: $0.name) },
                                    selected: model.selected?.projectId ?? "", dismiss: dismissSelection) { id in
                                        model.selected?.projectId = id
                                        model.selected?.projectName = model.projects.first { $0.id == id }?.name
                                    }
                            }
                        }.frame(maxWidth: 560).frame(maxHeight: geometry.size.height * 0.65)
                            .padding(16)
                            .transition(reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity))
                    }.accessibilityAddTraits(.isModal)
                        .accessibilityAction(.escape) { dismissSelection() }
                }
            }
    }

    private func dismissSelection() {
        showModelPicker = false
        showProjectPicker = false
    }

    private func sidebar(home: Bool) -> some View {
        let searchQuery = ChatPageQuery("search", value: search.trimmingCharacters(in: .whitespacesAndNewlines))
        let recentRows = sidebarChats(model.pageChats(ChatPageQuery()), search: "", expanded: expandedAgents)
        let pinnedRows = sidebarChats(model.pageChats(ChatPageQuery("pinned")), search: "", expanded: expandedAgents)
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                if home {
                    SuzentWordmark()
                    Spacer()
                } else {
                    SuzentLogoMark().frame(width: 24, height: 24)
                    Text("SUZENT").font(.system(size: 14, weight: .bold)).tracking(2)
                    Spacer()
                }
                Button { composing = false; showSettings = true; showSidebar = false } label: {
                    Image(systemName: "gearshape").font(.system(size: 20)).frame(width: 44, height: 44)
                }.buttonStyle(.plain).accessibilityLabel("Settings")
            }.padding(.horizontal, 20).padding(.top, 4).padding(.bottom, 4)
            if model.isDemo && home {
                HStack {
                    Text("Offline demo · Scripted replies, no AI calls").font(.footnote)
                    Spacer()
                    Button("Exit demo") { model.exitDemo() }.font(.footnote.bold()).disabled(model.busy)
                }.padding(.horizontal, 16).padding(.vertical, 8)
            }
            if home, let error = model.error {
                SuzentNotice(message: error) { model.error = nil }
            }
            if let regent = model.chats.first(where: { $0.isRegent }) {
                Button { openSidebarChat(regent) } label: {
                    RegentIdentity(working: regent.isRunning == true || (model.selected?.isRegent == true && model.streaming),
                                   waiting: regent.regent?.waiting ?? 0, unread: model.selected?.isRegent == true ? 0 : regent.regent?.unread ?? 0,
                                   lastMessageAt: regent.regent?.lastMessageAt, expanded: false)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 14).padding(.horizontal, 4)
                        .overlay(alignment: .trailing) { Image(systemName: "chevron.right").font(.system(size: 12)).foregroundStyle(Color.suzentMuted) }
                        .overlay(alignment: .bottom) { Rectangle().fill(Color.suzentText.opacity(0.08)).frame(height: 1) }
                }.buttonStyle(.plain).disabled(model.busy).padding(.horizontal, 16)
            }
            Button { composing = false; Task { await model.createChat(); showSidebar = false; showSettings = false } } label: {
                Label("New conversation", systemImage: "square.and.pencil")
                    .font(.system(size: home ? 16 : PresentationTokens.typeCaption, weight: .semibold))
                    .foregroundStyle(Color.black)
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .padding(.horizontal, 12)
                    .background(Color(presentation: PresentationTokens.yellow), in: RoundedRectangle(cornerRadius: 6))
            }.buttonStyle(.plain)
                .disabled(model.busy || model.device?.permissions.createChats != true)
                .padding(.horizontal, 16).padding(.top, 12)
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(Color.suzentMuted)
                TextField("Search chats", text: $search).font(.system(size: home ? 16 : 14))
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
            }.padding(.horizontal, 12).frame(height: 42)
                .background(Color.suzentText.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                .padding(.horizontal, 16).padding(.vertical, 12)
            ScrollViewReader { reader in
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Color.clear.frame(height: 0).id("sidebar-top")
                    if !search.isEmpty {
                        sidebarHeading("Search results")
                        let rows = sidebarChats(model.pageChats(searchQuery), search: search, expanded: expandedAgents)
                        conversationRows(rows)
                        pageFooter(searchQuery)
                        if rows.isEmpty && model.chatPages[searchQuery] != nil {
                            Text("No matching chats").font(.subheadline).foregroundStyle(Color.suzentMuted)
                        }
                    } else {
                        if !pinnedRows.isEmpty {
                            sidebarHeading("Pinned")
                            conversationRows(pinnedRows)
                            pageFooter(ChatPageQuery("pinned"))
                        }
                        let recent = recentRows.filter { $0.depth == 0 }
                        if !recent.isEmpty {
                            HStack {
                                sidebarHeading("Recent")
                                Spacer()
                                if (model.chatPages[ChatPageQuery()]?.total ?? 0) > 3 {
                                    Button(showAllRecent ? "Show fewer" : "View all") { showAllRecent.toggle() }
                                        .font(.caption).foregroundStyle(Color.suzentMuted).frame(minHeight: 44)
                                }
                            }
                            let recentIDs = Set((showAllRecent ? recent : Array(recent.prefix(3))).map { $0.chat.id })
                            conversationRows(recentRows.filter { recentIDs.contains($0.root.id) })
                        }
                        if showAllRecent { pageFooter(ChatPageQuery()) }
                        if !projects.isEmpty { sidebarHeading("Projects") }
                        VStack(alignment: .leading, spacing: 2) {
                            ForEach(projects) { project in
                                projectSection(project, rows: sidebarChats(model.pageChats(ChatPageQuery("project", value: project.id)), search: "", expanded: expandedAgents))
                            }
                        }
                        if pinnedRows.isEmpty && recentRows.isEmpty {
                            Text("No chats yet").font(.subheadline).foregroundStyle(Color.suzentMuted).padding(.vertical, 24)
                        }
                    }
                    scheduledSection
                }.padding(.horizontal, 16)
            }
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
    }

    @ViewBuilder private func pageFooter(_ query: ChatPageQuery) -> some View {
        if model.loadingPages.contains(query) {
            ProgressView().frame(maxWidth: .infinity, minHeight: 44).accessibilityLabel("Loading conversations")
        } else if model.chatPages[query]?.nextOffset != nil || model.chatPages[query] == nil {
            Button("Load more") { Task { await model.loadPage(query, more: model.chatPages[query] != nil) } }
                .font(.caption).foregroundStyle(Color.suzentMuted).frame(maxWidth: .infinity, minHeight: 44)
        }
    }

    private func projectSection(_ project: Project, rows: [SidebarChatEntry]) -> some View {
        let projectOpen = expandedProject == project.id
        let isOpen = projectOpen || !search.isEmpty
        return VStack(alignment: .leading, spacing: 0) {
            Button {
                expandedProject = projectOpen ? nil : project.id
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "folder").font(.system(size: 17)).padding(.trailing, 6)
                    Text(project.name).lineLimit(1).truncationMode(.tail)
                    Spacer()
                    Text("\(project.chatCount ?? rows.count)").font(.caption).foregroundStyle(Color.suzentMuted)
                    Image(systemName: isOpen ? "chevron.down" : "chevron.right").font(.system(size: 10)).foregroundStyle(Color.suzentMuted)
                }
                .font(.system(size: PresentationTokens.typeCaption, weight: .semibold))
                .foregroundStyle(Color.suzentText)
                .padding(.horizontal, 4)
                .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
            }.buttonStyle(SuzentRowButtonStyle())
            if isOpen {
                conversationRows(rows)
                pageFooter(ChatPageQuery("project", value: project.id))
            }
        }.task(id: "\(isOpen):\(model.navigationVersion)") {
            if isOpen { await model.loadPage(ChatPageQuery("project", value: project.id)) }
        }
    }

    private func conversationRows(_ entries: [SidebarChatEntry]) -> some View {
        ForEach(entries) { entry in
            let chat = entry.chat
            VStack(alignment: .leading, spacing: 0) {
                ChatSidebarRow(chat: chat, selected: model.selected?.id == chat.id && !showSettings,
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
            }
        }
    }

    private func openSidebarChat(_ chat: Chat) {
        composing = false
        showSettings = false
        showSidebar = false
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

    private func sidebarHeading(_ title: LocalizedStringKey, count: Int? = nil) -> some View {
        HStack(spacing: 8) {
            Text(title).font(.system(size: 11, weight: .semibold))
                .textCase(.uppercase).tracking(0.8).foregroundStyle(Color.suzentMuted)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let count {
                Text("\(count)").font(.system(size: PresentationTokens.typeSidebarSection, weight: .bold))
                    .foregroundStyle(Color.suzentMuted)
            }
        }
    }

    /// Desktop status line order: paused (with failure) → failed → next run → active;
    /// a running task keeps the marker and still reports the schedule.
    private func scheduledTaskStatus(_ task: ScheduledTask) -> String {
        if !task.active { return task.unresolvedError ? "Paused · Failed" : "Paused" }
        if task.unresolvedError { return "Last run failed" }
        if let raw = task.nextRunAt, let date = taskDate(raw) {
            return "Next run \(date.formatted(date: .abbreviated, time: .shortened))"
        }
        return "Active"
    }

    private func scheduledTaskActivity(_ task: ScheduledTask) -> String {
        let raw = task.failureHandled ? task.chatUpdatedAt : task.lastRunAt
        return raw.flatMap(taskDate)?.formatted(date: .abbreviated, time: .shortened) ?? "Not yet"
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
                }.font(.system(size: 14, weight: .medium)).frame(minHeight: 48)
            }.buttonStyle(.plain).accessibilityValue(scheduledExpanded ? Text("Expanded") : Text("Collapsed"))
            ForEach(scheduledExpanded || !search.isEmpty ? visible : []) { group in
                VStack(alignment: .leading, spacing: 0) {
                    if let task = group.task {
                        Button {
                            if let id = task.chatId { openSidebarChat(model.chats.first { $0.id == id } ?? Chat(id: id, title: task.name)) }
                        } label: {
                            HStack(alignment: .top) {
                                VStack(alignment: .leading, spacing: 0) {
                                    Text(task.name).font(.system(size: PresentationTokens.typeCaption, weight: .medium))
                                        .lineLimit(1).truncationMode(.tail)
                                    HStack(spacing: 6) {
                                        if task.isRunning { Rectangle().fill(Color.suzentLink).frame(width: 8, height: 8) }
                                        Text(scheduledTaskStatus(task)).lineLimit(1).truncationMode(.tail)
                                        if let root = group.root, root.childCount > 0 {
                                            Text("·")
                                            SidebarFoldControl(count: root.childCount, expanded: expandedAgents.contains(root.id), toggle: {}).hidden()
                                                .anchorPreference(key: SidebarFoldAnchorKey.self, value: .bounds) { $0 }
                                        }
                                    }.font(.system(size: PresentationTokens.typeSidebarSection, weight: .medium))
                                        .foregroundStyle(Color.suzentMuted)
                                    if task.chatId == nil {
                                        Text("No conversation yet").font(.system(size: PresentationTokens.typeSidebarSection, weight: .medium))
                                            .foregroundStyle(Color.suzentMuted)
                                    }
                                }.frame(maxWidth: .infinity, alignment: .leading)
                                Text(scheduledTaskActivity(task))
                                    .font(.system(size: PresentationTokens.typeSidebarSection, weight: .medium)).monospacedDigit()
                                    .foregroundStyle(Color.suzentMuted).lineLimit(1).padding(.leading, 8)
                            }.padding(.horizontal, 12).padding(.vertical, PresentationTokens.spaceRow).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        }.buttonStyle(ChatRowButtonStyle(selected: task.chatId != nil && model.selected?.id == task.chatId && !showSettings))
                            .disabled(model.busy || task.chatId == nil)
                            .overlayPreferenceValue(SidebarFoldAnchorKey.self) { anchor in
                                GeometryReader { proxy in
                                    if let anchor, let root = group.root {
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
                    } else if let root = group.root { conversationRows([root]) }
                    conversationRows(group.children)
                }
            }
            if scheduledExpanded && search.isEmpty && groups.count > previewLimit {
                Button { showAllScheduled.toggle() } label: {
                    Text(showAllScheduled ? "Show fewer" : "View all \(groups.count) scheduled tasks")
                        .font(.system(size: PresentationTokens.typeCaption, weight: .bold))
                        .frame(maxWidth: .infinity, minHeight: PresentationTokens.controlHeight)
                }.buttonStyle(.plain)
            }
        }
    }

    private func taskDate(_ raw: String) -> Date? {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return parser.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    }

    private var settings: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Settings").font(.system(size: PresentationTokens.typeSection, weight: .bold))
                if model.isDemo {
                    Text("Explore with sample data. No desktop, API key, or internet required.")
                    Text("Pairing and Node connections require a real desktop. Attachments stay on this device and are not analysed.")
                        .font(.footnote).foregroundStyle(Color.suzentMuted)
                    Button("Reset demo") { Task { await model.resetDemo() } }.buttonStyle(SuzentButtonStyle()).disabled(model.busy)
                    Button("Exit demo") { model.exitDemo() }.buttonStyle(SuzentButtonStyle()).disabled(model.busy)
                } else {
                    SuzentDisclosure(title: "Desktop access") {
                        if let device = model.device { ClientPermissionsView(device: device, origin: model.origin) }
                    }
                    VStack(alignment: .leading, spacing: 12) {
                        Text("This phone as a Node").font(.system(size: PresentationTokens.typeControl, weight: .bold))
                        Toggle("Enable foreground Node", isOn: Binding(get: { model.nodeEnabled }, set: { model.toggleNode($0) })).toggleStyle(SuzentToggleStyle())
                        Text(model.nodeStatus).font(.system(size: PresentationTokens.typeCaption)).foregroundStyle(Color.suzentMuted)
                    }.padding(16).overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                    Button("Pair again") { model.error = nil; repairScanner = true }.buttonStyle(SuzentButtonStyle()).disabled(model.busy || model.streaming)
                    Button("Forget connection", role: .destructive) { model.forget() }.buttonStyle(SuzentButtonStyle(quiet: true, destructive: true)).disabled(model.busy)
                    Text("To revoke access, also remove its credentials on the desktop.").font(.footnote).foregroundStyle(Color.suzentMuted)
                    SuzentDisclosure(title: "About") {
                        Button("Try offline demo") { Task { await model.startDemo() } }
                            .font(.system(size: PresentationTokens.typeCaption))
                            .foregroundStyle(Color.suzentMuted).frame(minHeight: 44)
                            .buttonStyle(.plain).disabled(model.busy || model.streaming)
                    }
                }
            }.padding(PresentationTokens.spacePage)
        }
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
                                }.font(.system(size: 13)).frame(minHeight: 44)
                            }.buttonStyle(.plain).disabled(model.busy)
                        }
                    }.font(.system(size: 12)).padding(.horizontal, 16).padding(.vertical, 8)
                }
            }
            FollowingChatScrollView(openedVersion: model.openedVersion, sentVersion: model.sentVersion,
                                   startsAtBottom: !chat.id.isEmpty, dismissKeyboard: { composing = false; attachmentsExpanded = false }) {
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
                        ApprovalCards(model: model)
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(16)
            }.id(chat.id)
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
                        .font(.system(size: PresentationTokens.typeChat)).padding(.horizontal, 4).padding(.vertical, 12).frame(minHeight: 44).disabled(model.busy)
                    if !composing { sendAction(chat) } else { Color.clear.frame(width: 44, height: 44) }
                }
                if composing { HStack(spacing: 8) {
                    Button {
                        composing = false; showModelPicker = true
                    } label: {
                        HStack(spacing: 6) {
                            Text(model.selectedModel ?? chat.model ?? String(localized: "Desktop model")).lineLimit(1).truncationMode(.middle)
                            Image(systemName: "chevron.down").font(.system(size: 10, weight: .semibold))
                        }.font(.system(size: 12, weight: .medium)).foregroundStyle(Color.suzentMuted).frame(minHeight: 44)
                    }.buttonStyle(.plain)
                    .disabled(model.busy || model.streaming || (chat.models ?? []).isEmpty || model.device?.permissions.send != true)
                    Spacer(minLength: 8)
                    sendAction(chat)
                } }
            }.padding(10).background(Color.suzentSurface)
                .animation(reduceMotion ? nil : .easeInOut(duration: 0.18), value: composing)
                .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                .background { Rectangle().fill(Color.suzentShadow).offset(x: 2, y: 2) }
                .padding(.trailing, 2).padding(.bottom, 2)
                .padding(.horizontal, 12).padding(.bottom, 8)
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
    private func startPage(_ chat: Chat) -> some View {
        VStack(spacing: 28) {
            GreetingCube(engaged: keyboardVisible).frame(width: keyboardVisible ? 90 : 160, height: keyboardVisible ? 90 : 160)
            TimelineView(.periodic(from: .now, by: 60)) { context in
                let hour = Calendar.current.component(.hour, from: context.date)
                let greeting: LocalizedStringKey = hour < 5 ? "Night owl?" : hour < 12 ? "Good morning." : hour < 17 ? "Keep building." : hour < 21 ? "Good evening." : "Bed time? Or maybe late night coding?"
                Text(greeting).textCase(.uppercase).font(.system(size: 30, weight: .black))
                    .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }
            SuzentSelectionTrigger(value: chat.projectName ?? "Home", prefix: String(localized: "Creating in")) {
                composing = false; showProjectPicker = true
            }.disabled(model.busy || model.projects.isEmpty)
            if model.isDemo {
                ForEach(model.demoPrompts, id: \.self) { prompt in
                    Button(prompt) { model.draft = prompt; Task { await model.send() } }
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
            Task { if stopping { await model.stop() } else { await model.send() } }
        } label: {
            Image(systemName: stopping ? "stop.fill" : "arrow.up")
                .font(.system(size: stopping ? 14 : 20, weight: .bold)).foregroundStyle(.white)
                .frame(width: 36, height: 36)
                .background(stopping ? Color.red : Color.suzentLink)
                .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 2))
                .padding(4).contentShape(Rectangle())
        }.buttonStyle(.plain).disabled(!enabled).opacity(enabled ? 1 : 0.45)
            .accessibilityLabel(stopping ? String(localized: "Stop") : String(localized: "Send"))
    }

}
