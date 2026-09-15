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
            VStack(spacing: 0) {
                SuzentWordmark().frame(maxWidth: .infinity).padding(.vertical, 16)
                Rectangle().frame(height: PresentationTokens.borderWidth)
                if model.connected {
                    HStack(spacing: 8) {
                        Button("Chats") { model.selected = nil }
                            .disabled(model.streaming || model.busy)
                        Spacer()
                        Button("Access") { showAccess = true }
                        Button("Refresh", systemImage: "arrow.clockwise") { Task { await model.refresh() } }
                            .labelStyle(.iconOnly)
                    }.buttonStyle(SuzentButtonStyle(compact: true)).padding(16)
                }
                Group {
                    if !model.connected { connectionForm }
                    else if let chat = model.selected { conversation(chat) }
                    else { chatList }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .toolbar(.hidden, for: .navigationBar)
            .safeAreaInset(edge: .bottom) {
                if let error = model.error {
                    HStack {
                        Text(error).font(.footnote)
                        Button("Dismiss") { model.error = nil }
                    }.buttonStyle(SuzentButtonStyle(prominent: true, compact: true))
                .padding(16)
                .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                .padding(16)
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
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                Text("Conversations").font(.caption.bold()).foregroundStyle(.secondary)
                    .padding(.vertical, 12)
                Button("New conversation", systemImage: "square.and.pencil") { Task { await model.createChat() } }
                    .buttonStyle(SuzentButtonStyle(prominent: true))
                    .disabled(model.busy || model.device?.permissions.createChats != true)
                    .padding(.bottom, 16)
                ForEach(model.chats) { chat in
                    Button { Task { await model.open(chat) } } label: {
                        HStack {
                            Text(chat.title).font(.headline).multilineTextAlignment(.leading)
                            Spacer()
                            if chat.isRunning == true { ProgressView() }
                        }.frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
                            .padding(.vertical, 8)
                    }.buttonStyle(.plain)
                    Divider()
                }
            }.padding(.horizontal, 16)
        }
        .refreshable { await model.refresh() }
    }

    private func conversation(_ chat: Chat) -> some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: PresentationTokens.spaceLarge) {
                    Text(chat.title).font(.title2.bold())
                    ForEach(Array(presentMessages(chat.messages ?? []).enumerated()), id: \.offset) { _, message in
                        MessageView(message: message)
                    }
                    if model.streaming || !model.liveText.isEmpty {
                        SuzentMarkdown(text: model.liveText.isEmpty ? String(localized: "Working…") : model.liveText)
                    }
                }.padding()
            }
            VStack(alignment: .trailing, spacing: 12) {
                TextField("Message", text: $model.draft, axis: .vertical).lineLimit(2...6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .font(.body)
                if model.streaming || chat.isRunning == true {
                    Button("Stop") { Task { await model.stop() } }.disabled(model.device?.permissions.stop != true)
                } else {
                    Button("Send") { Task { await model.send() } }
                        .disabled(model.device?.permissions.send != true || model.busy || model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }.buttonStyle(SuzentButtonStyle(prominent: true, compact: true))
                .padding(16)
                .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
                .padding(16)
        }
    }
}
