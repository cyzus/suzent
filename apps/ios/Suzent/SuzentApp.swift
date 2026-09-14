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
    @State private var showAccess = false

    var body: some View {
        NavigationStack {
            Group {
                if !model.connected { connectionForm }
                else if let chat = model.selected { conversation(chat) }
                else { chatList }
            }
            .navigationTitle("Suzent")
            .toolbar {
                if model.connected {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Chats") { model.selected = nil }
                            .disabled(model.streaming || model.busy)
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Access", systemImage: "iphone.gen3") { showAccess = true }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Refresh", systemImage: "arrow.clockwise") { Task { await model.refresh() } }
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                if let error = model.error {
                    HStack {
                        Text(error).font(.footnote)
                        Button("Dismiss") { model.error = nil }
                    }.padding().background(.regularMaterial)
                }
            }
        }
        .tint(Color(presentation: PresentationTokens.blue))
        .sheet(isPresented: $showAccess) {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: PresentationTokens.spaceLarge) {
                        if let device = model.device {
                            ClientPermissionsView(device: device, origin: model.origin)
                                .padding().overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                        }
                        VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
                            Text("This phone as a Node").font(.headline)
                            Toggle("Enable foreground Node", isOn: Binding(get: { model.nodeEnabled }, set: { model.toggleNode($0) }))
                            Text(model.nodeStatus).font(.footnote)
                        }.padding().overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                        Button("Forget connection", role: .destructive) { model.forget(); showAccess = false }.disabled(model.busy)
                        Text("To revoke access, also remove its credentials on the desktop.").font(.footnote)
                    }.padding(PresentationTokens.spacePage)
                }
                .navigationTitle("Desktop access")
                .toolbar { Button("Done") { showAccess = false } }
            }
        }
        .onChange(of: model.connected) { _, connected in if !connected { showAccess = false } }
    }

    private var connectionForm: some View { PairingView(model: model) }

    private var chatList: some View {
        List {
            Section("Conversations") {
                Button("New conversation", systemImage: "plus") { Task { await model.createChat() } }
                    .disabled(model.busy || model.device?.permissions.createChats != true)
                    .opacity(model.device?.permissions.createChats == true ? 1 : 0.4)
                ForEach(model.chats) { chat in
                    Button { Task { await model.open(chat) } } label: {
                        HStack {
                            Text(chat.title)
                            Spacer()
                            if chat.isRunning == true { ProgressView() }
                        }
                    }
                }
            }
        }
        .listStyle(.plain)
        .refreshable { await model.refresh() }
    }

    private func conversation(_ chat: Chat) -> some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 18) {
                    Text(chat.title).font(.title2.bold())
                    ForEach(Array(presentMessages(chat.messages ?? []).enumerated()), id: \.offset) { _, message in
                        MessageView(message: message)
                    }
                    if model.streaming || !model.liveText.isEmpty {
                        Markdown(model.liveText.isEmpty ? String(localized: "Working…") : model.liveText).textSelection(.enabled)
                    }
                }.padding()
            }
            HStack {
                TextField("Message", text: $model.draft, axis: .vertical).lineLimit(1...6)
                if model.streaming || model.chats.first(where: { $0.id == chat.id })?.isRunning == true {
                    Button("Stop") { Task { await model.stop() } }.disabled(model.device?.permissions.stop != true)
                } else {
                    Button("Send", systemImage: "arrow.up.circle.fill") { Task { await model.send() } }
                        .disabled(model.device?.permissions.send != true || model.busy || model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }.padding().background(.regularMaterial)
        }
    }
}
