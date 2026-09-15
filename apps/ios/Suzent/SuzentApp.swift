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
    @State private var search = ""
    @State private var collapsedProjects: Set<String> = []
    @FocusState private var composing: Bool
    @State private var keyboardVisible = false

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
                                Button("Forget connection", role: .destructive) { model.forget() }.disabled(model.busy)
                            }.frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                        else if !model.connected { PairingView(model: model) }
                        else if showSettings { settings }
                        else if let chat = model.selected { conversation(chat) }
                        else {
                            VStack(spacing: 20) {
                                SuzentAssistantBadge()
                                Text("Choose a conversation from the sidebar.").foregroundStyle(.secondary)
                                Button("New conversation", systemImage: "square.and.pencil") { Task { await model.createChat() } }
                                    .buttonStyle(SuzentButtonStyle(prominent: true))
                                    .disabled(model.busy || model.streaming || model.device?.permissions.createChats != true)
                            }.padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                if !wide && model.connected {
                    Color.black.opacity(showSidebar ? 0.3 : 0).ignoresSafeArea()
                        .allowsHitTesting(showSidebar)
                        .onTapGesture { withAnimation { showSidebar = false } }
                    sidebar.frame(width: min(geometry.size.width - 48, 330), height: geometry.size.height)
                        .background(Color(uiColor: .systemBackground))
                        .overlay(alignment: .trailing) { Rectangle().frame(width: 2) }
                        .compositingGroup()
                        .offset(x: showSidebar ? 0 : -min(geometry.size.width - 48, 330) - 2)
                        .allowsHitTesting(showSidebar)
                        .accessibilityHidden(!showSidebar)
                }
            }.clipped()
        }
        .task { if model.canReconnect && !model.connected { await model.connect() } }
        .tint(Color(presentation: PresentationTokens.blue))
        .task(id: model.connected) { if model.connected { await model.watchNavigation() } }
        .onChange(of: model.connected) { _, connected in showSidebar = connected; if !connected { showSettings = false } }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in keyboardVisible = true }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in keyboardVisible = false }
        .onChange(of: model.sentVersion) { _, _ in composing = false }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Chats").font(.title2.bold())
                Spacer()
                Button { withAnimation { showSidebar = false } } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }
                    .accessibilityLabel("Close sidebar")
            }.padding(.horizontal, 16)
            TextField("Search chats", text: $search).padding(12)
                .overlay(Rectangle().stroke(.secondary.opacity(0.4))).padding(.horizontal, 16).padding(.bottom, 12)
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
                    Text(chat.title).lineLimit(2).multilineTextAlignment(.leading)
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
                Text("Settings").font(.title2.bold())
                DisclosureGroup("Desktop access") {
                    if let device = model.device { ClientPermissionsView(device: device, origin: model.origin).padding(.top, 16) }
                }.padding(16).overlay(Rectangle().stroke(.secondary.opacity(0.4)))
                VStack(alignment: .leading, spacing: 12) {
                    Text("This phone as a Node").font(.headline)
                    Toggle("Enable foreground Node", isOn: Binding(get: { model.nodeEnabled }, set: { model.toggleNode($0) }))
                    Text(model.nodeStatus).font(.footnote).foregroundStyle(.secondary)
                }
                Button("Forget connection", role: .destructive) { model.forget() }.disabled(model.busy)
                Text("To revoke access, also remove its credentials on the desktop.").font(.footnote).foregroundStyle(.secondary)
            }.padding(20)
        }
    }

    private func conversation(_ chat: Chat) -> some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    if let project = chat.projectName { Text(project).font(.caption).foregroundStyle(.secondary) }
                    Text(chat.id.isEmpty ? String(localized: "New conversation") : chat.title).font(.headline).lineLimit(1)
                }
                Spacer()
            }.padding(.horizontal, 16).padding(.vertical, 10)
            ScrollViewReader { reader in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: PresentationTokens.spaceLarge) {
                        ForEach(Array(presentMessages(chat.messages ?? [], liveToolIds: Set(model.liveParts.filter { $0.type == "tool" }.compactMap(\.toolCallId))).enumerated()), id: \.offset) { _, message in MessageView(message: message) }
                        if model.streaming || !model.liveParts.isEmpty {
                            if model.liveParts.isEmpty { Text("Working…").foregroundStyle(.secondary) }
                            else { ActivityContent(parts: model.liveParts, live: model.streaming) }
                        }
                        ApprovalCards(model: model)
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(16)
                }.contentShape(Rectangle())
                    .simultaneousGesture(TapGesture().onEnded { composing = false })
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: model.sentVersion) { _, _ in withAnimation { reader.scrollTo("bottom", anchor: .bottom) } }
            }
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .bottom) {
                    TextField("Message", text: $model.draft, axis: .vertical).lineLimit(keyboardVisible ? 1...6 : 1...1).focused($composing)
                        .font(.callout).padding(.vertical, 6).disabled(model.busy)
                    if !keyboardVisible { sendAction(chat) }
                }
                if keyboardVisible { HStack {
                    Menu {
                        Button("Conversation default") { model.selectedModel = nil }
                        ForEach(chat.models ?? [], id: \.self) { name in
                            Button { model.selectedModel = name } label: {
                                if model.selectedModel == name { Label(name, systemImage: "checkmark") } else { Text(name) }
                            }
                        }
                    } label: {
                        HStack { Text(model.selectedModel ?? chat.model ?? String(localized: "Desktop model")).lineLimit(1); Image(systemName: "chevron.down") }.font(.caption.bold())
                            .frame(minHeight: 44)
                    }.buttonStyle(.plain).disabled(model.busy || model.streaming || (chat.models ?? []).isEmpty || model.device?.permissions.send != true)
                    Spacer(minLength: 8)
                    sendAction(chat)
                } }
            }.padding(keyboardVisible ? 12 : 6).overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                .padding(.horizontal, 12).padding(.bottom, 8)
        }.task(id: chat.id) { await model.watchApprovals(chat.id) }
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
