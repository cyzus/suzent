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

private struct ChatSidebarRow: View {
    let chat: Chat
    let selected: Bool
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

    var body: some View {
        Button { if !menu { open() } } label: {
            HStack {
                if chat.pinned == true { Image(systemName: "pin.fill").font(.caption) }
                Text(chat.title).font(.system(size: PresentationTokens.typeChat, weight: selected ? .semibold : .regular))
                    .lineLimit(2).multilineTextAlignment(.leading)
                Spacer()
                if chat.isRunning == true { Image(systemName: "ellipsis") }
            }.padding(12).frame(maxWidth: .infinity, minHeight: 48, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(ChatRowButtonStyle(selected: selected)).disabled(!enabled)
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
            .overlay(Rectangle().stroke(Color.primary, lineWidth: 2))
            .background {
                Rectangle().fill(Color.black).offset(x: 3, y: 3)
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
    @State private var showSidebar = false
    @State private var showSettings = false
    @State private var repairScanner = false
    @State private var search = ""
    @State private var collapsedProjects: Set<String> = []
    @FocusState private var composing: Bool
    @State private var keyboardVisible = false
    @State private var showModelPicker = false
    @State private var showProjectPicker = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var projects: [Project] {
        var result = model.projects
        for chat in model.chats {
            if let id = chat.projectId, !result.contains(where: { $0.id == id }) {
                result.append(Project(id: id, name: chat.projectName ?? id))
            }
        }
        return result
    }

    var body: some View {
        GeometryReader { geometry in
            let wide = geometry.size.width >= 760
            ZStack(alignment: .leading) {
                HStack(spacing: 0) {
                    if wide && model.connected { sidebar.frame(width: 280); Divider() }
                    VStack(spacing: 0) {
                        HStack {
                            if model.connected && !wide {
                                Button { composing = false; withAnimation { showSidebar = true } } label: {
                                    Image(systemName: "line.3.horizontal").frame(width: 44, height: 44)
                                }.accessibilityLabel("Open sidebar")
                            }
                            Spacer(); SuzentWordmark(); Spacer()
                            if model.connected {
                                Button { composing = false; Task { await model.createChat(); showSettings = false; showSidebar = false } } label: {
                                    Image(systemName: "square.and.pencil").frame(width: 44, height: 44)
                                }.accessibilityLabel("New conversation")
                                    .disabled(model.busy || model.streaming || model.device?.permissions.createChats != true)
                            }
                        }.padding(.horizontal, 12).padding(.vertical, 6)
                        Rectangle().frame(height: PresentationTokens.borderWidth)
                        if let error = model.error {
                            SuzentNotice(message: error) { model.error = nil }
                        }
                        if !model.connected && model.canReconnect {
                            VStack(spacing: 20) {
                                SuzentAssistantBadge()
                                Text("Reconnect to desktop").font(.system(size: PresentationTokens.typeSection, weight: .bold))
                                if model.busy {
                                    StreamingPulse()
                                    if model.reconnecting {
                                        Button("Cancel") { model.cancelReconnect() }
                                            .buttonStyle(SuzentButtonStyle())
                                    }
                                }
                                else { Button("Reconnect to desktop") { Task { await model.connect() } }.buttonStyle(SuzentButtonStyle(prominent: true)) }
                                Button("Pair again") { model.error = nil; repairScanner = true }.buttonStyle(SuzentButtonStyle()).disabled(model.busy || model.streaming)
                Button("Forget connection", role: .destructive) { model.forget() }.buttonStyle(SuzentButtonStyle(quiet: true, destructive: true)).disabled(model.busy)
                            }.padding(PresentationTokens.spaceLarge).frame(maxWidth: 480).frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                        else if !model.connected { PairingView(model: model) }
                        else if showSettings { settings }
                        else if let chat = model.selected { conversation(chat) }
                        else {
                            if model.busy { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
                            else { Text("Select a conversation or start a new one.").foregroundStyle(.secondary).padding().frame(maxWidth: .infinity, maxHeight: .infinity) }
                        }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                if !wide && model.connected {
                    Color.black.opacity(showSidebar ? 0.3 : 0).ignoresSafeArea()
                        .allowsHitTesting(showSidebar)
                        .onTapGesture { withAnimation { showSidebar = false } }
                    sidebar.frame(width: min(geometry.size.width - 48, PresentationTokens.sidebarWidth), height: geometry.size.height)
                        .background(Color.suzentSurface)
                        .overlay(alignment: .trailing) { Rectangle().frame(width: 2) }
                        .compositingGroup()
                        .offset(x: showSidebar ? 0 : -min(geometry.size.width - 48, PresentationTokens.sidebarWidth) - 2)
                        .allowsHitTesting(showSidebar)
                        .accessibilityHidden(!showSidebar)
                }
            }.background(Color.suzentSurface).clipped()
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
        .tint(.primary)
        .task(id: model.connected) { if model.connected { await model.watchNavigation() } }
        .onChange(of: model.connected) { _, connected in showModelPicker = false; showProjectPicker = false; showSidebar = false; if !connected { showSettings = false } }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in keyboardVisible = true }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in keyboardVisible = false }
        .accessibilityHidden(showModelPicker || showProjectPicker)
        .overlay { selectionOverlay }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: showModelPicker || showProjectPicker)
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

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Chats").font(.system(size: PresentationTokens.typeSection, weight: .bold))
                Spacer()
                Button { withAnimation { showSidebar = false } } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }
                    .accessibilityLabel("Close sidebar")
            }.padding(.horizontal, 16)
            SuzentTextInput(placeholder: "Search chats", text: $search).padding(.horizontal, 16).padding(.bottom, 12)
            ScrollViewReader { reader in
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Color.clear.frame(height: 0).id("sidebar-top")
                    if model.chats.contains(where: { $0.pinned == true }) {
                        Text("Pinned").font(.system(size: PresentationTokens.typeControl, weight: .bold, design: .monospaced))
                        conversationRows(model.chats.filter { $0.pinned == true })
                        Divider()
                    }
                    ForEach(projects) { project in projectSection(project) }
                    let unassigned = model.chats.filter { $0.projectId == nil && $0.pinned != true }
                    if !unassigned.isEmpty { conversationRows(unassigned) }
                    if projects.isEmpty && model.chats.isEmpty {
                        Button("New conversation") { Task { await model.createChat(); showSidebar = false; showSettings = false } }
                            .disabled(model.busy || model.streaming || model.device?.permissions.createChats != true)
                    }
                }.padding(.horizontal, 16)
            }
            .onChange(of: model.pinnedVersion) { _, _ in
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.22)) {
                    reader.scrollTo("sidebar-top", anchor: .top)
                }
            }
            }
            Divider()
            Button { composing = false; showSettings = true; showSidebar = false } label: {
                Label("Settings", systemImage: "gearshape").font(.headline).frame(maxWidth: .infinity, alignment: .leading).padding(20)
            }.buttonStyle(.plain)
        }
    }

    private func projectSection(_ project: Project) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Button {
                    if collapsedProjects.contains(project.id) { collapsedProjects.remove(project.id) }
                    else { collapsedProjects.insert(project.id) }
                } label: {
                    HStack { Image(systemName: collapsedProjects.contains(project.id) ? "chevron.right" : "chevron.down"); Text(project.name).lineLimit(2) }
                        .font(.system(.subheadline, design: .monospaced).bold()).frame(minHeight: 44)
                }.buttonStyle(.plain)
                Spacer()
                Button { Task { await model.createChat(projectID: project.id); showSidebar = false; showSettings = false } } label: {
                    Image(systemName: "plus").frame(width: 44, height: 44)
                }.accessibilityLabel("New conversation")
                    .disabled(model.busy || model.streaming || model.device?.permissions.createChats != true || !model.projects.contains(where: { $0.id == project.id }))
            }
            if !collapsedProjects.contains(project.id) || !search.isEmpty { conversationRows(model.chats.filter { $0.projectId == project.id && $0.pinned != true }) }
        }
    }

    private func conversationRows(_ chats: [Chat]) -> some View {
        ForEach(chats.filter { search.isEmpty || $0.title.localizedCaseInsensitiveContains(search) }.sorted { ($0.pinned == true) && ($1.pinned != true) }) { chat in
            ChatSidebarRow(chat: chat, selected: model.selected?.id == chat.id && !showSettings,
                           enabled: !model.busy, canManage: model.device?.permissions.manageChats == true,
                           projects: model.projects, manage: { action, value in
                Task { await model.manageChat(chat, action: action, value: value) }
            }) {
                composing = false
                showSettings = false
                showSidebar = false
                Task { await model.open(chat) }
            }
        }
    }

    private var settings: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Settings").font(.system(size: PresentationTokens.typeSection, weight: .bold))
                SuzentDisclosure(title: "Desktop access") {
                    if let device = model.device { ClientPermissionsView(device: device, origin: model.origin) }
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("This phone as a Node").font(.system(size: PresentationTokens.typeControl, weight: .bold))
                    Toggle("Enable foreground Node", isOn: Binding(get: { model.nodeEnabled }, set: { model.toggleNode($0) })).toggleStyle(SuzentToggleStyle())
                    Text(model.nodeStatus).font(.system(size: PresentationTokens.typeCaption)).foregroundStyle(.secondary)
                }.padding(16).overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                Button("Pair again") { model.error = nil; repairScanner = true }.buttonStyle(SuzentButtonStyle()).disabled(model.busy || model.streaming)
                Button("Forget connection", role: .destructive) { model.forget() }.buttonStyle(SuzentButtonStyle(quiet: true, destructive: true)).disabled(model.busy)
                Text("To revoke access, also remove its credentials on the desktop.").font(.footnote).foregroundStyle(.secondary)
            }.padding(PresentationTokens.spacePage)
        }
    }

    private func conversation(_ chat: Chat) -> some View {
        VStack(spacing: 0) {
            if !chat.id.isEmpty { HStack {
                VStack(alignment: .leading, spacing: 3) {
                    if let project = chat.projectName { Text(project).font(.caption).foregroundStyle(.secondary) }
                    Text(chat.id.isEmpty ? String(localized: "New conversation") : chat.title).font(.headline).lineLimit(1)
                }
                Spacer()
            }.padding(.horizontal, 16).padding(.vertical, 10) }
            FollowingChatScrollView(openedVersion: model.openedVersion, sentVersion: model.sentVersion,
                                   startsAtBottom: !chat.id.isEmpty, dismissKeyboard: { composing = false }) {
                    LazyVStack(alignment: .leading, spacing: PresentationTokens.spaceLarge) {
                        if chat.id.isEmpty { startPage(chat) }
                        let messages = presentMessages(chat.messages ?? [], liveToolIds: Set(model.liveParts.filter { $0.type == "tool" }.compactMap(\.toolCallId)))
                        let hasLiveMessage = model.streaming || !model.liveParts.isEmpty
                        ForEach(Array(messages.enumerated()), id: \.offset) { index, message in
                            let idle = !model.busy && !hasLiveMessage && chat.isRunning != true
                            let lastUser = (chat.messages ?? []).lastIndex { $0.role == "user" }
                            let canReplay = idle && !(chat.models ?? []).isEmpty && lastUser != nil && model.device?.permissions.send == true && model.device?.permissions.manageChats == true
                            MessageView(message: message, isLatest: !hasLiveMessage && index == messages.count - 1, fallbackModel: chat.model,
                                canRetry: canReplay && (message.messageIndex == lastUser || (index == messages.count - 1 && message.role == "assistant")),
                                canEdit: canReplay && message.role == "user" && message.messageIndex == lastUser,
                                canFork: idle && message.role == "assistant" && model.device?.permissions.createChats == true,
                                onAction: { action, text in Task { await model.messageAction(message, action: action, text: text) } })
                        }
                        if hasLiveMessage {
                            VStack(alignment: .leading, spacing: 10) {
                                AssemblyBadge(thinking: showAssemblyBadge(model.liveParts, streaming: model.streaming))
                                if !model.liveParts.isEmpty { ActivityContent(parts: model.liveParts, live: model.streaming) }
                            }
                        }
                        ApprovalCards(model: model)
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(16)
            }.id(chat.id)
            VStack(alignment: .leading, spacing: 8) {
                PendingAttachmentStrip(model: model)
                HStack(alignment: .center) {
                    if model.attachmentsSupported && model.device?.permissions.send == true { AttachMenu(model: model) }
                    TextField("Message", text: $model.draft, axis: .vertical).lineLimit(keyboardVisible ? 1...6 : 1...1).focused($composing)
                        .tint(Color(presentation: PresentationTokens.blue))
                        .font(.system(size: PresentationTokens.typeChat)).padding(.horizontal, 4).padding(.vertical, 12).frame(minHeight: 44).disabled(model.busy)
                    if !keyboardVisible { sendAction(chat) }
                }
                if keyboardVisible { HStack {
                    SuzentSelectionTrigger(value: model.selectedModel ?? chat.model ?? String(localized: "Desktop model")) {
                        composing = false; showModelPicker = true
                    }.disabled(model.busy || model.streaming || (chat.models ?? []).isEmpty || model.device?.permissions.send != true)
                    Spacer(minLength: 8)
                    sendAction(chat)
                } }
            }.padding(10).background(Color.suzentSurface)
                .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                .background { Rectangle().fill(Color.primary).offset(x: 2, y: 2) }
                .padding(.trailing, 2).padding(.bottom, 2)
                .padding(.horizontal, 12).padding(.bottom, 8)
        }.task(id: chat.id) { await model.watchApprovals(chat.id) }
    }
    private func startPage(_ chat: Chat) -> some View {
        VStack(spacing: 28) {
            GreetingCube().frame(width: keyboardVisible ? 90 : 160, height: keyboardVisible ? 90 : 160)
            TimelineView(.periodic(from: .now, by: 60)) { context in
                let hour = Calendar.current.component(.hour, from: context.date)
                let greeting: LocalizedStringKey = hour < 5 ? "Night owl?" : hour < 12 ? "Good morning." : hour < 17 ? "Keep building." : hour < 21 ? "Good evening." : "Bed time? Or maybe late night coding?"
                Text(greeting).textCase(.uppercase).font(.system(size: 30, weight: .black))
                    .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }
            SuzentSelectionTrigger(value: chat.projectName ?? String(localized: "Default"), prefix: String(localized: "Creating in")) {
                composing = false; showProjectPicker = true
            }.disabled(model.busy || model.projects.isEmpty)
        }.frame(maxWidth: .infinity).padding(.horizontal, 8).padding(.vertical, keyboardVisible ? 12 : 40)
    }

    @ViewBuilder private func sendAction(_ chat: Chat) -> some View {
        Group {
            if model.streaming || chat.isRunning == true {
                Button("Stop") { Task { await model.stop() } }.disabled(model.device?.permissions.stop != true)
            } else {
                Button("Send") { Task { await model.send() } }
                    .disabled(model.busy || model.device?.permissions.send != true || (model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && model.attachments.isEmpty))
            }
        }.buttonStyle(SuzentButtonStyle(prominent: true, compact: true))
    }

}
