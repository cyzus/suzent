import QuickLook
import SwiftUI
import SuzentCore

private func permissionModeLabel(_ mode: String) -> String {
    switch mode {
    case "auto": String(localized: "Smart")
    case "full_access": String(localized: "Full access")
    default: String(localized: "Ask")
    }
}

private func permissionModeDescription(_ mode: String) -> String {
    switch mode {
    case "auto": String(localized: "Classify unresolved actions automatically; hard safety rules still apply.")
    case "full_access": String(localized: "Run tool actions without approval prompts; explicit denies still apply.")
    default: String(localized: "Ask before state-changing tool actions.")
    }
}

private func statusLabel(_ status: String) -> String {
    switch status {
    case "active": String(localized: "Active")
    case "paused": String(localized: "Paused")
    case "completed": String(localized: "Completed")
    case "running": String(localized: "Running")
    case "queued": String(localized: "Queued")
    case "failed": String(localized: "Failed")
    case "cancelled": String(localized: "Cancelled")
    case "in_progress": String(localized: "In progress")
    case "blocked": String(localized: "Blocked")
    case "pending": String(localized: "Pending")
    default: status.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

private func taskStatusSymbol(_ status: String) -> (name: String, color: Color) {
    switch status {
    case "completed": ("checkmark.circle.fill", .green)
    case "in_progress", "running", "queued": ("circle.dotted.circle", .blue)
    case "blocked", "waiting": ("pause.circle", .orange)
    case "failed", "cancelled": ("xmark.circle", .red)
    default: ("circle", Color.suzentMuted)
    }
}

/// The phone's version of the desktop chat side panel, opened from the conversation header.
struct ChatDetailsSheet: View {
    let model: MobileModel
    let chat: Chat
    @Environment(\.dismiss) private var dismiss
    @State private var details: ChatDetails?
    @State private var failure: String?
    @State private var savingMode = false

    var body: some View {
        NavigationStack {
            Group {
                if let details { content(details) }
                else if let failure {
                    ContentUnavailableView {
                        Label("Couldn't load details", systemImage: "exclamationmark.triangle")
                    } description: { Text(failure) } actions: {
                        Button("Retry") { Task { await load() } }
                    }
                } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
            }
            .background(Color.suzentBackground)
            .navigationTitle("Conversation details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .task { await load() }
    }

    private func load() async {
        failure = nil
        do { details = try await model.chatDetails(chat.id) }
        catch is CancellationError { }
        catch { failure = error.localizedDescription }
    }

    private func setMode(_ mode: String) {
        guard var current = details, current.permissionMode.mode != mode, !savingMode else { return }
        savingMode = true
        Task {
            defer { savingMode = false }
            do {
                let saved = try await model.setPermissionMode(chat.id, mode: mode)
                current.permissionMode.mode = saved
                details = current
            } catch { model.error = error.localizedDescription }
        }
    }

    @ViewBuilder private func content(_ details: ChatDetails) -> some View {
        List {
            Section {
                if details.permissionMode.canChange {
                    Picker("Approval mode", selection: Binding(get: { details.permissionMode.mode }, set: setMode)) {
                        ForEach(details.permissionMode.available, id: \.self) { Text(permissionModeLabel($0)).tag($0) }
                    }.disabled(savingMode)
                } else {
                    LabeledContent("Approval mode", value: permissionModeLabel(details.permissionMode.mode))
                }
            } header: { Text("Tools") } footer: {
                Text(permissionModeDescription(details.permissionMode.mode)
                     + (details.permissionMode.canChange ? "" : " " + String(localized: "Changing it needs the Approve tool requests permission.")))
            }

            if let context = details.context {
                Section("Context") {
                    VStack(alignment: .leading, spacing: 8) {
                        ProgressView(value: Double(context.percent), total: 100).tint(Color.suzentText)
                        Text("\(context.percent)% of \(context.limit.formatted(.number.notation(.compactName))) tokens")
                            .font(.footnote).foregroundStyle(Color.suzentMuted)
                    }.padding(.vertical, 4)
                }
            }

            if details.goal != nil || !details.tasks.isEmpty {
                Section("Tasks") {
                    if let goal = details.goal {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(goal.objective).font(.body.weight(.semibold))
                            Text(statusLabel(goal.status)).font(.footnote).foregroundStyle(Color.suzentMuted)
                        }
                    }
                    ForEach(details.tasks) { task in
                        let symbol = taskStatusSymbol(task.status)
                        Label {
                            Text(task.status == "in_progress" ? task.activeForm ?? task.title : task.title)
                                .strikethrough(task.status == "completed", color: Color.suzentMuted)
                                .foregroundStyle(task.status == "completed" ? Color.suzentMuted : Color.suzentText)
                        } icon: { Image(systemName: symbol.name).foregroundStyle(symbol.color) }
                    }
                }
            }

            if !details.agents.isEmpty {
                Section("Background tasks") {
                    ForEach(details.agents) { agent in
                        let symbol = taskStatusSymbol(agent.status)
                        let row = Label {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(agent.description).lineLimit(2)
                                Text(statusLabel(agent.status))
                                    .font(.footnote).foregroundStyle(Color.suzentMuted)
                            }
                        } icon: { Image(systemName: symbol.name).foregroundStyle(symbol.color) }
                        if let child = agent.chatId {
                            Button {
                                dismiss()
                                Task { await model.open(model.chats.first { $0.id == child } ?? Chat(id: child, title: agent.description)) }
                            } label: { row }.foregroundStyle(Color.suzentText)
                        } else { row }
                    }
                }
            }

            if let memory = details.memory, !memory.recalled.isEmpty || !memory.saved.isEmpty {
                Section("Memory") {
                    ForEach(memory.recalled, id: \.self) { item in
                        Label(item.content, systemImage: "arrow.down.circle").labelStyle(MemoryLabelStyle())
                    }
                    ForEach(memory.saved, id: \.self) { item in
                        Label(item.content, systemImage: "plus.circle").labelStyle(MemoryLabelStyle())
                    }
                }
            }

            if details.files {
                Section {
                    NavigationLink {
                        WorkspaceFolderView(model: model, chatID: chat.id, path: "")
                    } label: { Label("Files", systemImage: "folder") }
                } footer: { Text("Files in this conversation's project workspace on your desktop.") }
            }
        }
        .scrollContentBackground(.hidden)
        .refreshable { await load() }
    }
}

private struct MemoryLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            configuration.icon.foregroundStyle(Color.suzentMuted)
            configuration.title.font(.subheadline)
        }
    }
}

struct WorkspaceFolderView: View {
    let model: MobileModel
    let chatID: String
    let path: String
    @State private var listing: WorkspaceListing?
    @State private var failure: String?
    @State private var opening: String?
    @State private var preview: URL?

    var body: some View {
        Group {
            if let listing {
                if listing.entries.isEmpty {
                    ContentUnavailableView("No files yet", systemImage: "folder")
                } else {
                    List {
                        ForEach(listing.entries) { entry in row(entry) }
                        if listing.truncated {
                            Text("Only the first 500 items are shown.").font(.footnote).foregroundStyle(Color.suzentMuted)
                        }
                    }.scrollContentBackground(.hidden)
                }
            } else if let failure {
                ContentUnavailableView {
                    Label("Couldn't load files", systemImage: "exclamationmark.triangle")
                } description: { Text(failure) } actions: {
                    Button("Retry") { Task { await load() } }
                }
            } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
        }
        .background(Color.suzentBackground)
        .navigationTitle(path.isEmpty ? String(localized: "Files") : (path as NSString).lastPathComponent)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
        .quickLookPreview($preview)
    }

    private func load() async {
        failure = nil
        do { listing = try await model.workspaceFiles(chatID, path: path) }
        catch is CancellationError { }
        catch { failure = error.localizedDescription }
    }

    @ViewBuilder private func row(_ entry: WorkspaceEntry) -> some View {
        let child = workspaceChildPath(path, entry.name)
        if entry.isDir {
            NavigationLink {
                WorkspaceFolderView(model: model, chatID: chatID, path: child)
            } label: { Label(entry.name, systemImage: "folder") }
        } else {
            Button {
                guard opening == nil else { return }
                opening = child
                Task {
                    defer { opening = nil }
                    do { preview = try await model.downloadWorkspaceFile(chatID, path: child) }
                    catch { model.error = error.localizedDescription }
                }
            } label: {
                HStack {
                    Label(entry.name, systemImage: "doc")
                    Spacer()
                    if opening == child { ProgressView() }
                    else {
                        Text(Int64(entry.size).formatted(.byteCount(style: .file)))
                            .font(.footnote).foregroundStyle(Color.suzentMuted)
                    }
                }
            }.foregroundStyle(Color.suzentText).disabled(opening != nil)
        }
    }
}
