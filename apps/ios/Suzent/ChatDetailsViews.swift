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

/// The desktop side panel's square status marker: blue while working, red on failure, yellow when held up.
private struct StatusMarker: View {
    let status: String

    var body: some View {
        switch status {
        case "in_progress", "running", "queued", "active":
            Rectangle().fill(Color.suzentLink).frame(width: 8, height: 8)
        case "failed", "cancelled":
            Rectangle().fill(Color.suzentDanger).frame(width: 8, height: 8)
        case "blocked", "waiting", "paused":
            Rectangle().fill(Color(presentation: PresentationTokens.yellow)).frame(width: 8, height: 8)
                .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 1))
        case "completed":
            Rectangle().fill(Color.suzentMuted.opacity(0.5)).frame(width: 8, height: 8)
        default:
            Rectangle().stroke(Color.suzentMuted, lineWidth: 1).frame(width: 8, height: 8)
        }
    }
}

private struct DetailsHeading: View {
    let title: LocalizedStringKey
    init(_ title: LocalizedStringKey) { self.title = title }

    var body: some View {
        Text(title).textCase(.uppercase).tracking(1.6)
            .suzentFont(PresentationTokens.typeSidebarSection, weight: .heavy)
            .foregroundStyle(Color.suzentMuted)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, PresentationTokens.spacePage).padding(.top, 20).padding(.bottom, 6)
            .accessibilityAddTraits(.isHeader)
    }
}

private struct RowDivider: View {
    var body: some View { Rectangle().fill(Color.suzentRowDivider).frame(height: 1) }
}

/// The black title bar shared with the desktop-model and project pickers.
private struct DetailsBar: View {
    let title: String
    var back: (() -> Void)?
    let close: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            if let back {
                Button(action: back) { Image(systemName: "chevron.left").frame(width: 44, height: 44) }
                    .accessibilityLabel("Back")
            }
            Text(title).suzentFont(15, weight: .bold, design: .monospaced).lineLimit(1).truncationMode(.middle)
                .padding(.leading, back == nil ? 16 : 0).accessibilityAddTraits(.isHeader)
            Spacer()
            Button(action: close) { Image(systemName: "xmark").frame(width: 44, height: 44) }.accessibilityLabel("Dismiss")
        }.padding(.top, 12).foregroundStyle(.white).background(.black)
    }
}

private struct DetailsMessage: View {
    let text: String
    var retry: (() -> Void)?

    var body: some View {
        VStack(spacing: 12) {
            Text(text).suzentFont(PresentationTokens.typeCaption).foregroundStyle(Color.suzentMuted).multilineTextAlignment(.center)
            if let retry {
                Button("Retry", action: retry).suzentFont(PresentationTokens.typeControl, weight: .semibold)
                    .padding(.horizontal, 16).frame(minHeight: 40)
                    .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                    .buttonStyle(.plain)
            }
        }.padding(32).frame(maxWidth: .infinity)
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
    @State private var folders: [String] = []

    var body: some View {
        VStack(spacing: 0) {
            if let folder = folders.last {
                DetailsBar(title: folder.isEmpty ? String(localized: "Files") : (folder as NSString).lastPathComponent,
                           back: { folders.removeLast() }, close: { dismiss() })
                WorkspaceFolderView(model: model, chatID: chat.id, path: folder) { folders.append($0) }.id(folder)
            } else {
                DetailsBar(title: String(localized: "Conversation details"), close: { dismiss() })
                ScrollView {
                    if let details { content(details) }
                    else if let failure { DetailsMessage(text: failure) { Task { await load() } } }
                    else { ProgressView().padding(40) }
                }.refreshable { await load() }
            }
        }
        .background(Color.suzentSurface)
        .foregroundStyle(Color.suzentText)
        .task { await load() }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .presentationCornerRadius(PresentationTokens.radius)
        .presentationBackground(Color.suzentSurface)
    }

    private func load() async {
        failure = nil
        do { details = try await model.chatDetails(chat.id) }
        catch is CancellationError { }
        catch { failure = String(localized: "Couldn't load details") }
    }

    private func setMode(_ mode: String) {
        guard var current = details, current.permissionMode.mode != mode, !savingMode else { return }
        savingMode = true
        Task {
            defer { savingMode = false }
            do {
                current.permissionMode.mode = try await model.setPermissionMode(chat.id, mode: mode)
                details = current
            } catch { model.error = error.localizedDescription }
        }
    }

    private func modePicker(_ mode: ChatDetails.PermissionMode) -> some View {
        HStack(spacing: 0) {
            ForEach(Array(mode.available.enumerated()), id: \.element) { index, option in
                let chosen = option == mode.mode
                Button { setMode(option) } label: {
                    Text(permissionModeLabel(option)).suzentFont(PresentationTokens.typeCaption, weight: chosen ? .bold : .medium)
                        .lineLimit(1).minimumScaleFactor(0.8)
                        .frame(maxWidth: .infinity, minHeight: 40)
                        .foregroundStyle(chosen ? Color.black : Color.suzentText)
                        .background(chosen ? Color(presentation: PresentationTokens.yellow) : Color.suzentSurface)
                        .overlay(alignment: .leading) {
                            if index > 0 { Rectangle().fill(Color.suzentOutline).frame(width: PresentationTokens.borderWidth) }
                        }
                }.buttonStyle(.plain)
                    .disabled(!mode.canChange || savingMode)
                    .accessibilityAddTraits(chosen ? .isSelected : [])
            }
        }
        .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
        .opacity(mode.canChange ? 1 : PresentationTokens.disabledAlpha)
        .padding(.horizontal, PresentationTokens.spacePage)
    }

    private func statusRow(_ title: String, status: String, detail: String? = nil, done: Bool = false) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            StatusMarker(status: status).alignmentGuide(.firstTextBaseline) { $0[.bottom] - 1 }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).suzentFont(PresentationTokens.typeChat).lineLimit(2)
                    .strikethrough(done, color: Color.suzentMuted)
                    .foregroundStyle(done ? Color.suzentMuted : Color.suzentText)
                if let detail {
                    Text(detail).suzentFont(PresentationTokens.typeMeta, weight: .medium).foregroundStyle(Color.suzentMuted)
                }
            }
            Spacer(minLength: 0)
        }.padding(.horizontal, PresentationTokens.spacePage).padding(.vertical, PresentationTokens.spaceRow)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
    }

    @ViewBuilder private func content(_ details: ChatDetails) -> some View {
        LazyVStack(alignment: .leading, spacing: 0) {
            DetailsHeading("Approval mode")
            modePicker(details.permissionMode)
            Text(permissionModeDescription(details.permissionMode.mode)
                 + (details.permissionMode.canChange ? "" : " " + String(localized: "Changing it needs the Approve tool requests permission.")))
                .suzentFont(PresentationTokens.typeLabel).foregroundStyle(Color.suzentMuted)
                .padding(.horizontal, PresentationTokens.spacePage).padding(.top, 8)

            if let context = details.context {
                DetailsHeading("Context")
                VStack(alignment: .leading, spacing: 8) {
                    GeometryReader { proxy in
                        Rectangle().fill(Color.suzentText)
                            .frame(width: proxy.size.width * CGFloat(context.percent) / 100)
                    }.frame(height: 10)
                        .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
                    Text("\(context.percent)% of \(context.limit.formatted(.number.notation(.compactName))) tokens")
                        .suzentFont(PresentationTokens.typeLabel).monospacedDigit().foregroundStyle(Color.suzentMuted)
                }.padding(.horizontal, PresentationTokens.spacePage)
            }

            if details.goal != nil || !details.tasks.isEmpty {
                DetailsHeading("Tasks")
                if let goal = details.goal {
                    Text(goal.objective).suzentFont(PresentationTokens.typeControl, weight: .bold)
                        .padding(.horizontal, PresentationTokens.spacePage).padding(.bottom, 2)
                    Text(statusLabel(goal.status)).suzentFont(PresentationTokens.typeMeta, weight: .medium)
                        .foregroundStyle(Color.suzentMuted).padding(.horizontal, PresentationTokens.spacePage)
                }
                ForEach(details.tasks) { task in
                    statusRow(task.status == "in_progress" ? task.activeForm ?? task.title : task.title,
                              status: task.status, done: task.status == "completed")
                    RowDivider()
                }
            }

            if !details.agents.isEmpty {
                DetailsHeading("Background tasks")
                ForEach(details.agents) { agent in
                    if let child = agent.chatId {
                        Button {
                            dismiss()
                            Task { await model.open(model.chats.first { $0.id == child } ?? Chat(id: child, title: agent.description)) }
                        } label: {
                            HStack(spacing: 0) {
                                statusRow(agent.description, status: agent.status, detail: statusLabel(agent.status))
                                Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(Color.suzentMuted).padding(.trailing, PresentationTokens.spacePage)
                            }
                        }.buttonStyle(ChatRowButtonStyle(selected: false))
                    } else {
                        statusRow(agent.description, status: agent.status, detail: statusLabel(agent.status))
                    }
                    RowDivider()
                }
            }

            if let memory = details.memory, !memory.recalled.isEmpty || !memory.saved.isEmpty {
                DetailsHeading("Memory")
                ForEach(Array((memory.recalled + memory.saved).enumerated()), id: \.offset) { _, item in
                    Text(item.content).suzentFont(PresentationTokens.typeChat)
                        .padding(.horizontal, PresentationTokens.spacePage).padding(.vertical, PresentationTokens.spaceRow)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    RowDivider()
                }
            }

            if details.files {
                DetailsHeading("Files")
                Button { folders = [""] } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "folder").font(.system(size: 15, weight: .medium))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Project workspace").suzentFont(PresentationTokens.typeControl, weight: .semibold)
                            Text("Files in this conversation's project workspace on your desktop.")
                                .suzentFont(PresentationTokens.typeMeta, weight: .medium).foregroundStyle(Color.suzentMuted)
                                .multilineTextAlignment(.leading)
                        }
                        Spacer(minLength: 8)
                        Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold)).foregroundStyle(Color.suzentMuted)
                    }.padding(.horizontal, PresentationTokens.spacePage).frame(maxWidth: .infinity, minHeight: 56)
                        .contentShape(Rectangle())
                }.buttonStyle(ChatRowButtonStyle(selected: false))
                RowDivider()
            }
        }.padding(.bottom, PresentationTokens.spaceLarge)
    }
}

struct WorkspaceFolderView: View {
    let model: MobileModel
    let chatID: String
    let path: String
    let open: (String) -> Void
    @State private var listing: WorkspaceListing?
    @State private var failure: String?
    @State private var opening: String?
    @State private var preview: URL?

    var body: some View {
        ScrollView {
            if let listing {
                if listing.entries.isEmpty { DetailsMessage(text: String(localized: "No files yet")) }
                else {
                    LazyVStack(spacing: 0) {
                        ForEach(listing.entries) { entry in row(entry); RowDivider() }
                        if listing.truncated {
                            Text("Only the first 500 items are shown.").suzentFont(PresentationTokens.typeLabel)
                                .foregroundStyle(Color.suzentMuted).padding(PresentationTokens.spacePage)
                        }
                    }
                }
            } else if let failure { DetailsMessage(text: failure) { Task { await load() } } }
            else { ProgressView().padding(40) }
        }
        .task { await load() }
        .refreshable { await load() }
        .quickLookPreview($preview)
    }

    private func load() async {
        failure = nil
        do { listing = try await model.workspaceFiles(chatID, path: path) }
        catch is CancellationError { }
        catch { failure = String(localized: "Couldn't load files") }
    }

    private func row(_ entry: WorkspaceEntry) -> some View {
        let child = workspaceChildPath(path, entry.name)
        return Button {
            if entry.isDir { open(child); return }
            guard opening == nil else { return }
            opening = child
            Task {
                defer { opening = nil }
                do { preview = try await model.downloadWorkspaceFile(chatID, path: child) }
                catch { model.error = error.localizedDescription }
            }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: entry.isDir ? "folder" : "doc").font(.system(size: 15, weight: .medium)).frame(width: 20)
                Text(entry.name).suzentFont(PresentationTokens.typeChat).lineLimit(1).truncationMode(.middle)
                Spacer(minLength: 8)
                if opening == child { ProgressView() }
                else if entry.isDir {
                    Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold)).foregroundStyle(Color.suzentMuted)
                } else {
                    Text(Int64(entry.size).formatted(.byteCount(style: .file)))
                        .suzentFont(PresentationTokens.typeMeta, weight: .medium).monospacedDigit().foregroundStyle(Color.suzentMuted)
                }
            }.padding(.horizontal, PresentationTokens.spacePage).frame(maxWidth: .infinity, minHeight: 48).contentShape(Rectangle())
        }.buttonStyle(ChatRowButtonStyle(selected: false)).disabled(opening != nil && opening != child)
    }
}
