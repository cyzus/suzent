import SwiftUI
import SuzentCore

private enum InboxSection: String, CaseIterable {
    case notifications, tasks, all
    var title: LocalizedStringKey {
        switch self {
        case .notifications: "Notifications"
        case .tasks: "Tasks"
        case .all: "All events"
        }
    }
}

struct MailboxView<TaskContent: View>: View {
    @Bindable var model: MobileModel
    let openChat: (Chat) -> Void
    @ViewBuilder let tasks: () -> TaskContent
    @State private var expanded: Set<String> = []
    @State private var section: InboxSection = .notifications

    var body: some View {
        VStack(spacing: 0) {
            VStack(spacing: 4) {
                Text("Inbox").suzentFont(15, weight: .semibold)
                if let desktop = model.activeDesktop, !model.isDemo {
                    Text(desktop.name).suzentFont(11).foregroundStyle(Color.suzentMuted).lineLimit(1)
                }
            }.frame(maxWidth: .infinity, minHeight: 52)
            Rectangle().fill(Color.suzentOutline).frame(height: 1)
            SuzentSegmentedTabs(options: InboxSection.allCases, selection: Binding(get: { section }, set: { item in
                section = item; expanded = []
                if item != .tasks { Task { await model.changeMailbox(category: item.rawValue) } }
            }), enabled: !model.mailboxBusy, title: { $0.title })
                .padding(.horizontal, 16).padding(.vertical, 12)
            if section == .tasks {
                tasks()
            } else if !model.mailboxSupported {
                ContentUnavailableView("Inbox unavailable", systemImage: "tray", description: Text("Update the desktop to use the mobile inbox."))
            } else {
                messages
            }
        }.background(Color.suzentSurface)
            .task {
                if section != .tasks { section = model.mailboxCategory == "all" ? .all : .notifications }
                await model.refreshMailbox()
            }
            .onChange(of: model.device?.deviceId) { _, _ in expanded = [] }
    }

    private var messages: some View {
        VStack(spacing: 0) {
            if model.mailbox.unread > 0 {
                HStack {
                    Text("Unread: \(model.mailbox.unread)").suzentFont(12).foregroundStyle(Color.suzentMuted)
                    Spacer()
                    Button("Mark all read") { Task { await model.readMailbox() } }
                        .suzentFont(12).foregroundStyle(Color.suzentText).disabled(model.mailboxBusy)
                }.padding(.horizontal, 20).padding(.vertical, 8)
            }
            ScrollView {
                LazyVStack(spacing: 0) {
                    if let error = model.mailboxError {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(error).foregroundStyle(.red).suzentFont(13)
                            Button("Refresh") { Task { await model.refreshMailbox() } }
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
                    }
                    if model.device?.permissions.allChats != true {
                        Text("Only events linked to shared conversations are shown.").suzentFont(12).foregroundStyle(Color.suzentMuted).padding(.horizontal, 20).padding(.vertical, 8)
                    }
                    if model.mailbox.items.isEmpty && model.mailboxError == nil && !model.mailboxLoading {
                        VStack(spacing: 16) {
                            Image(systemName: "tray").font(.system(size: 32)).opacity(0.5)
                            Text("No inbox messages").suzentFont(14)
                        }.foregroundStyle(Color.suzentMuted).frame(maxWidth: .infinity).padding(.vertical, 64)
                    }
                    ForEach(mailboxThreads(model.mailbox.items)) { thread in row(thread) }
                    if model.mailboxLoading { ProgressView().padding(16) }
                    else if model.mailbox.hasMore {
                        Button("Load more") { Task { await model.loadMoreMailbox() } }
                            .suzentFont(13).foregroundStyle(Color.suzentText).disabled(model.mailboxBusy).padding(16)
                    }

                }.padding(.bottom, 24)
            }.refreshable { await model.refresh() }
        }
    }

    private func row(_ thread: MailboxThread) -> some View {
        MailboxThreadCard(thread: thread, chats: model.mailboxChats, expanded: expanded.contains(thread.id), busy: model.mailboxBusy,
            toggle: {
                if expanded.contains(thread.id) { expanded.remove(thread.id) }
                else { expanded.insert(thread.id); if !thread.unreadIds.isEmpty { Task { await model.readMailbox(thread.unreadIds) } } }
            }, read: { ids in Task { await model.readMailbox(ids) } }, open: openChat)
    }
}
