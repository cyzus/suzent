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
                            HStack {
                                Text(error).font(.footnote)
                                Spacer()
                                Button("Dismiss") { model.error = nil }
                            }.padding(12).background(Color(presentation: PresentationTokens.yellow)).foregroundStyle(.black)
                        }
                        if !model.connected && model.canReconnect {
                            VStack(spacing: 20) {
                                Text("Reconnect to desktop").font(.headline)
                                if model.busy { ProgressView() }
                                else { Button("Reconnect to desktop") { Task { await model.connect() } } }
                                Button("Pair again") { repairScanner = true }.buttonStyle(SuzentButtonStyle()).disabled(model.busy || model.streaming)
                Button("Forget connection", role: .destructive) { model.forget() }.disabled(model.busy)
                            }.frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                        else if !model.connected { PairingView(model: model) }
                        else if showSettings { settings }
                        else if let chat = model.selected { conversation(chat) }
                        else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                if !wide && model.connected {
                    Color.black.opacity(showSidebar ? 0.3 : 0).ignoresSafeArea()
                        .allowsHitTesting(showSidebar)
                        .onTapGesture { withAnimation { showSidebar = false } }
                    sidebar.frame(width: min(geometry.size.width - 48, PresentationTokens.sidebarWidth), height: geometry.size.height)
                        .background(Color(uiColor: .systemBackground))
                        .overlay(alignment: .trailing) { Rectangle().frame(width: 2) }
                        .compositingGroup()
                        .offset(x: showSidebar ? 0 : -min(geometry.size.width - 48, PresentationTokens.sidebarWidth) - 2)
                        .allowsHitTesting(showSidebar)
                        .accessibilityHidden(!showSidebar)
                }
            }.clipped()
        }
        .task { if model.canReconnect && !model.connected { await model.connect() } }
        .tint(Color(presentation: PresentationTokens.blue))
        .task(id: model.connected) { if model.connected { await model.watchNavigation() } }
        .onChange(of: model.connected) { _, connected in showModelPicker = false; showSidebar = false; if !connected { showSettings = false } }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in keyboardVisible = true }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in keyboardVisible = false }
        .sheet(isPresented: $showModelPicker) {
            SuzentSelectionPanel(title: String(localized: "Desktop model"),
                options: [(id: "", title: String(localized: "Conversation default"))] + Array(Set(model.selected?.models ?? [])).sorted().map { (id: $0, title: $0) },
                selected: model.selectedModel ?? "") { model.selectedModel = $0.isEmpty ? nil : $0 }
        }
        .sheet(isPresented: $showProjectPicker) {
            SuzentSelectionPanel(title: String(localized: "Creating in"),
                options: model.projects.map { (id: $0.id, title: $0.name) }, selected: model.selected?.projectId ?? "") { id in
                model.selected?.projectId = id
                model.selected?.projectName = model.projects.first { $0.id == id }?.name
            }
        }
        .onChange(of: model.sentVersion) { _, _ in composing = false }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Chats").font(.system(size: PresentationTokens.typeSection, weight: .bold))
                Spacer()
                Button { withAnimation { showSidebar = false } } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }
                    .accessibilityLabel("Close sidebar")
            }.padding(.horizontal, 16)
            TextField("Search chats", text: $search).font(.system(size: PresentationTokens.typeChat)).padding(12)
                .frame(minHeight: PresentationTokens.controlHeight)
                .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth)).padding(.horizontal, 16).padding(.bottom, 12)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(projects) { project in projectSection(project) }
                    let unassigned = model.chats.filter { $0.projectId == nil }
                    if !unassigned.isEmpty { conversationRows(unassigned) }
                    if projects.isEmpty && model.chats.isEmpty {
                        Button("New conversation") { Task { await model.createChat(); showSidebar = false; showSettings = false } }
                            .disabled(model.busy || model.streaming || model.device?.permissions.createChats != true)
                    }
                }.padding(.horizontal, 16)
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
            if !collapsedProjects.contains(project.id) || !search.isEmpty { conversationRows(model.chats.filter { $0.projectId == project.id }) }
        }
    }

    private func conversationRows(_ chats: [Chat]) -> some View {
        ForEach(chats.filter { search.isEmpty || $0.title.localizedCaseInsensitiveContains(search) }) { chat in
            Button {
                composing = false
                Task { await model.open(chat); showSettings = false; showSidebar = false }
            } label: {
                HStack {
                    Text(chat.title).font(.system(size: PresentationTokens.typeChat, weight: model.selected?.id == chat.id ? .semibold : .regular)).lineLimit(2).multilineTextAlignment(.leading)
                    Spacer()
                    if chat.isRunning == true { Image(systemName: "ellipsis").foregroundStyle(.blue) }
                }.padding(12).frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
                    .background(model.selected?.id == chat.id && !showSettings ? Color.primary.opacity(0.08) : .clear)
                    .overlay(alignment: .leading) { if model.selected?.id == chat.id && !showSettings { Rectangle().frame(width: 3) } }
            }.buttonStyle(.plain).disabled(model.busy)
        }
    }

    private var settings: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Settings").font(.system(size: PresentationTokens.typeSection, weight: .bold))
                DisclosureGroup("Desktop access") {
                    if let device = model.device { ClientPermissionsView(device: device, origin: model.origin).padding(.top, 16) }
                }.padding(16).overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                VStack(alignment: .leading, spacing: 12) {
                    Text("This phone as a Node").font(.headline)
                    Toggle("Enable foreground Node", isOn: Binding(get: { model.nodeEnabled }, set: { model.toggleNode($0) }))
                    Text(model.nodeStatus).font(.footnote).foregroundStyle(.secondary)
                }
                Button("Pair again") { repairScanner = true }.buttonStyle(SuzentButtonStyle()).disabled(model.busy || model.streaming)
                Button("Forget connection", role: .destructive) { model.forget() }.disabled(model.busy)
                Text("To revoke access, also remove its credentials on the desktop.").font(.footnote).foregroundStyle(.secondary)
            }.padding(20)
        }.fullScreenCover(isPresented: $repairScanner) { PairingScanner(model: model) }
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
            ScrollViewReader { reader in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: PresentationTokens.spaceLarge) {
                        if chat.id.isEmpty { startPage(chat) }
                        let messages = presentMessages(chat.messages ?? [], liveToolIds: Set(model.liveParts.filter { $0.type == "tool" }.compactMap(\.toolCallId)))
                        let hasLiveMessage = model.streaming || !model.liveParts.isEmpty
                        ForEach(Array(messages.enumerated()), id: \.offset) { index, message in
                            MessageView(message: message, isLatest: !hasLiveMessage && index == messages.count - 1)
                        }
                        if hasLiveMessage {
                            VStack(alignment: .leading, spacing: 10) {
                                SuzentAssistantBadge()
                                if model.liveParts.isEmpty { HStack(spacing: 8) { StreamingPulse(); Text("Working…").foregroundStyle(.secondary) } }
                                else { ActivityContent(parts: model.liveParts, live: model.streaming) }
                            }
                        }
                        ApprovalCards(model: model)
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(16)
                }.contentShape(Rectangle())
                    .simultaneousGesture(TapGesture().onEnded { composing = false })
                    .scrollDismissesKeyboard(.interactively)
                    .defaultScrollAnchor(chat.id.isEmpty ? .top : .bottom)
                    .onChange(of: model.openedVersion) { _, _ in reader.scrollTo("bottom", anchor: .bottom) }
                    .onChange(of: model.sentVersion) { _, _ in withAnimation { reader.scrollTo("bottom", anchor: .bottom) } }
            }.id(chat.id)
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .center) {
                    TextField("Message", text: $model.draft, axis: .vertical).lineLimit(keyboardVisible ? 1...6 : 1...1).focused($composing)
                        .font(.system(size: PresentationTokens.typeChat)).padding(.horizontal, 4).padding(.vertical, 12).frame(minHeight: 44).disabled(model.busy)
                    if !keyboardVisible { sendAction(chat) }
                }
                if keyboardVisible { HStack {
                    Button { composing = false; showModelPicker = true } label: {
                        HStack { Text(model.selectedModel ?? chat.model ?? String(localized: "Desktop model")).lineLimit(1); Image(systemName: "chevron.down") }.font(.caption.bold())
                            .frame(minHeight: 44)
                    }.buttonStyle(.plain).disabled(model.busy || model.streaming || (chat.models ?? []).isEmpty || model.device?.permissions.send != true)
                    Spacer(minLength: 8)
                    sendAction(chat)
                } }
            }.padding(10).background(Color(uiColor: .systemBackground))
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
            Button { composing = false; showProjectPicker = true } label: {
                HStack(spacing: 8) {
                    Image(systemName: "cube")
                    Text("Creating in").foregroundStyle(.secondary)
                    Text(chat.projectName ?? String(localized: "Default")).lineLimit(1)
                    Image(systemName: "chevron.down")
                }.font(.system(size: PresentationTokens.typeControl, weight: .bold)).padding(12)
                    .foregroundStyle(.primary).background(Color(uiColor: .systemBackground))
                    .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                    .background { Rectangle().fill(Color.primary).offset(x: 2, y: 2) }
                    .padding(.trailing, 2).padding(.bottom, 2)
            }.disabled(model.busy || model.projects.isEmpty).buttonStyle(.plain)
        }.frame(maxWidth: .infinity).padding(.horizontal, 8).padding(.vertical, keyboardVisible ? 12 : 40)
    }

    @ViewBuilder private func sendAction(_ chat: Chat) -> some View {
        Group {
            if model.streaming || chat.isRunning == true {
                Button("Stop") { Task { await model.stop() } }.disabled(model.device?.permissions.stop != true)
            } else {
                Button("Send") { Task { await model.send() } }
                    .disabled(model.busy || model.device?.permissions.send != true || model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }.buttonStyle(SuzentButtonStyle(prominent: true, compact: true))
    }

}
