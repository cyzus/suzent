import SwiftUI
import SuzentCore

private enum InboxFilter: String, CaseIterable {
    case all, notifications, external, agent
    var title: LocalizedStringKey {
        switch self {
        case .all: "All"
        case .notifications: "Notifications"
        case .external: "External"
        case .agent: "Agent"
        }
    }
}

struct MailboxView<TaskContent: View>: View {
    @Bindable var model: MobileModel
    let openThread: (String) -> Void
    @ViewBuilder let tasks: () -> TaskContent
    @State private var showTasks = false

    var body: some View {
        VStack(spacing: 0) {
            header
            Rectangle().fill(Color.suzentOutline).frame(height: PresentationTokens.borderWidth)
            if showTasks {
                tasks()
            } else if !model.mailboxSupported {
                ContentUnavailableView("Inbox unavailable", systemImage: "tray", description: Text("Update the desktop to use the mobile inbox."))
            } else {
                filters
                messages
            }
        }.background(Color.suzentSurface)
            .task { await model.refreshMailbox() }
    }

    private var header: some View {
        ZStack {
            VStack(spacing: 4) {
                Text(showTasks ? "Tasks" : "Inbox").suzentFont(15, weight: .semibold)
                if let desktop = model.activeDesktop, !model.isDemo {
                    Text(desktop.name).suzentFont(11).foregroundStyle(Color.suzentMuted).lineLimit(1)
                }
            }.padding(.horizontal, 56)
            HStack {
                if showTasks {
                    headerButton("chevron.left", label: "Inbox") { showTasks = false }
                } else if model.mailboxSupported && model.mailbox.unread > 0 {
                    headerButton("checkmark", label: "Mark all read") { Task { await model.readMailbox() } }
                        .disabled(model.mailboxBusy)
                }
                Spacer()
                if !showTasks { headerButton("clock", label: "Tasks") { showTasks = true } }
            }.padding(.horizontal, 6)
        }.frame(maxWidth: .infinity, minHeight: 52)
    }

    private func headerButton(_ icon: String, label: LocalizedStringKey, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon).font(.system(size: 17, weight: .medium)).foregroundStyle(Color.suzentText)
                .frame(width: 44, height: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityLabel(label)
    }

    private var filters: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(InboxFilter.allCases, id: \.self) { filter in
                    let selected = model.mailboxCategory == filter.rawValue
                    Button {
                        guard !selected else { return }
                        Task { await model.changeMailbox(category: filter.rawValue) }
                    } label: {
                        HStack(spacing: 5) {
                            Text(filter.title).suzentFont(PresentationTokens.typeMeta, weight: selected ? .semibold : .regular, design: .monospaced)
                            if filter == .notifications && model.mailbox.unread > 0 { SuzentCountBadge(count: model.mailbox.unread) }
                        }
                        .foregroundStyle(selected ? Color.suzentTabBlockText : Color.suzentMuted)
                        .padding(.horizontal, 10).frame(minHeight: 30)
                        .background(selected ? Color.suzentTabBlock : Color.suzentSurface)
                        .overlay(Rectangle().strokeBorder(selected ? Color.suzentTabBlock : Color.suzentRowDivider, lineWidth: 1))
                        .contentShape(Rectangle())
                    }.buttonStyle(.plain).disabled(model.mailboxBusy)
                        .accessibilityAddTraits(selected ? [.isSelected, .isButton] : .isButton)
                }
            }.padding(.horizontal, 16).padding(.vertical, 10)
        }.dynamicTypeSize(...DynamicTypeSize.accessibility2)
    }

    private var messages: some View {
        let threads = mailboxThreads(model.mailbox.items)
        return ScrollView {
            LazyVStack(spacing: 0) {
                Rectangle().fill(Color.suzentRowDivider).frame(height: 1)
                if let error = model.mailboxError {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(error).foregroundStyle(Color.suzentDanger).suzentFont(13)
                        Button("Refresh") { Task { await model.refreshMailbox() } }.suzentFont(13).foregroundStyle(Color.suzentText)
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                }
                if threads.isEmpty && model.mailboxError == nil && !model.mailboxLoading {
                    VStack(spacing: 16) {
                        Image(systemName: "tray").font(.system(size: 32)).opacity(0.5)
                        Text("No inbox messages").suzentFont(14)
                    }.foregroundStyle(Color.suzentMuted).frame(maxWidth: .infinity).padding(.vertical, 64)
                }
                ForEach(threads) { thread in
                    Button { openThread(thread.id) } label: {
                        MailboxThreadRow(thread: thread, target: thread.latest.chatId.flatMap { model.mailboxChats[$0] })
                    }.buttonStyle(.plain)
                        .onAppear { if thread.id == threads.last?.id { Task { await model.loadMoreMailbox() } } }
                }
                if model.mailboxLoading { ProgressView().padding(16) }
                if model.device?.permissions.allChats != true {
                    Text("Only events linked to shared conversations are shown.").suzentFont(11).foregroundStyle(Color.suzentMuted)
                        .multilineTextAlignment(.center).padding(.horizontal, 32).padding(.vertical, 16)
                }
            }.padding(.bottom, 24)
        }.refreshable { await model.refresh() }
    }
}
