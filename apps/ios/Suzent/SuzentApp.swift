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
    }

    private var connectionForm: some View {
        Form {
            Section("Your desktop backend") {
                TextField("https://desktop.example", text: $model.origin)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                if model.needsHostToken {
                    SecureField("Remote host token", text: $model.token)
                    Text("Create a host token in desktop Settings → Devices. This credential grants full backend access.")
                        .font(.footnote).foregroundStyle(.secondary)
                } else {
                    Text("This simulator connects to the backend on your Mac using its trusted local connection.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Button("Connect") { Task { await model.connect() } }
                    .disabled(model.busy || (model.needsHostToken && model.token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
            }
        }
    }

    private var chatList: some View {
        List {
            Section("This phone as a Node") {
                Toggle("Enable foreground Node", isOn: Binding(get: { model.nodeEnabled }, set: { model.toggleNode($0) }))
                Text(model.nodeStatus).font(.footnote)
            }
            Section("Conversations") {
                Button("New conversation", systemImage: "plus") { Task { await model.createChat() } }
                    .disabled(model.busy)
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
            Section {
                Button("Forget connection", role: .destructive) { model.forget() }.disabled(model.busy)
                Text("To revoke access, also remove its credentials on the desktop.").font(.footnote)
            }
        }
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
                    if model.streaming {
                        Markdown(model.liveText.isEmpty ? String(localized: "Working…") : model.liveText).textSelection(.enabled)
                    }
                }.padding()
            }
            HStack {
                TextField("Message", text: $model.draft, axis: .vertical).lineLimit(1...6)
                if model.streaming || model.chats.first(where: { $0.id == chat.id })?.isRunning == true {
                    Button("Stop") { Task { await model.stop() } }
                } else {
                    Button("Send", systemImage: "arrow.up.circle.fill") { Task { await model.send() } }
                        .disabled(model.busy || model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }.padding().background(.regularMaterial)
        }
    }
}
