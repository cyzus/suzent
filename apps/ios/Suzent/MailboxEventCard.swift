import SwiftUI
import SuzentCore

struct MailboxEventCard: View {
    let item: MailboxItem
    let target: Chat?
    let expanded: Bool
    let busy: Bool
    let toggle: () -> Void
    let read: () -> Void
    let open: (Chat) -> Void
    var count: Int = 1
    var threadUnread: Bool? = nil
    var compact: Bool = false
    var history: AnyView? = nil
    @State private var original = false

    private var presentation: MailboxPresentation {
        item.display
    }

    var body: some View {
        VStack(spacing: 0) {
            Button(action: toggle) { header.padding(.horizontal, 4).padding(.vertical, 10).contentShape(Rectangle()) }
                .buttonStyle(.plain).accessibilityValue(expanded ? Text("Expanded") : Text("Collapsed"))
            if expanded, let history { history }
            if expanded && history == nil {
                Rectangle().fill(Color.suzentOutline.opacity(0.4)).frame(height: 0.5).padding(.horizontal, 14)
                details.padding(.horizontal, 14)
            }
        }.background((threadUnread ?? item.unread) || expanded ? Color.suzentText.opacity(0.025) : Color.clear)
            .overlay(alignment: .bottom) { Rectangle().fill(Color.suzentOutline.opacity(0.35)).frame(height: 0.5) }
            .padding(.horizontal, compact ? 0 : 16)
            .onChange(of: expanded) { _, _ in original = false }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                if !compact { Image(systemName: presentation.icon == "code" ? "arrow.triangle.branch" : "tray")
                    .font(.system(size: 12)).frame(width: 14, height: 14) }
                if compact {
                    if let name = presentation.detail {
                        HStack(spacing: 4) { if let action = actionTitle { Text(action) }; Text(name) }.suzentFont(11)
                    } else if let action = actionTitle { Text(action).suzentFont(11) }
                    else { Text(presentation.title).suzentFont(11) }
                } else { Text(presentation.context ?? presentation.source).suzentFont(11, weight: .medium).lineLimit(1) }
                Spacer(minLength: 4)
                if !compact && count > 1 { Text(String(format: String(localized: "%d events"), count)).suzentFont(10) }
                if threadUnread ?? item.unread { Rectangle().fill(Color.suzentTabBlock).frame(width: 5, height: 5).accessibilityLabel("Unread") }
                if let date = suzentParseDate(item.createdAt) { Text(date.suzentStamp).suzentFont(10) }
                Image(systemName: expanded ? "chevron.down" : "chevron.right").font(.system(size: 10))
            }.foregroundStyle(Color.suzentMuted)
            if !compact { Text(presentation.title).suzentFont(14, weight: .semibold).lineSpacing(2)
                .foregroundStyle(Color.suzentText).lineLimit(expanded ? nil : 2).frame(maxWidth: .infinity, alignment: .leading) }
            if !compact, count == 1, presentation.detail == nil, let action = actionTitle {
                Text(action).suzentFont(10).foregroundStyle(Color.suzentMuted)
            }
            if let name = presentation.detail, count == 1, !compact {
                HStack(spacing: 4) { if let action = actionTitle { Text(action) }; Text(name) }
                    .suzentFont(11).foregroundStyle(Color.suzentMuted)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 2) {
            if item.unread { Button("Mark read", action: read).suzentFont(12).foregroundStyle(Color.suzentText).disabled(busy).padding(.vertical, 10) }
            if item.chatId != nil {
                Button { if let target { open(target) } } label: {
                    HStack(spacing: 10) {
                        Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 16)).foregroundStyle(Color.suzentMuted)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Related conversation").suzentFont(10).foregroundStyle(Color.suzentMuted)
                            Text(target.flatMap { $0.title.isEmpty ? nil : $0.title } ?? String(localized: "Conversation unavailable"))
                                .suzentFont(13, weight: .medium).foregroundStyle(Color.suzentText).lineLimit(2)
                            if let project = target?.projectName, !project.isEmpty { Text(project).suzentFont(10).foregroundStyle(Color.suzentMuted) }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                        if target != nil { Image(systemName: "chevron.right").font(.system(size: 11)).foregroundStyle(Color.suzentMuted) }
                    }.frame(minHeight: 32).padding(.vertical, 12).contentShape(Rectangle())
                }.buttonStyle(.plain).disabled(target == nil)
            }
            if !item.payload.isEmpty {
                DisclosureGroup(isExpanded: $original) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(item.eventType).suzentFont(10).foregroundStyle(Color.suzentMuted)
                        Text(item.payload).font(.system(size: 12, design: .monospaced)).lineSpacing(3).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(10).background(Color.suzentText.opacity(0.04))
                    }.padding(.bottom, 14)
                } label: { Text("Original content").suzentFont(11).foregroundStyle(Color.suzentMuted).frame(minHeight: 44) }
                .tint(Color.suzentMuted)
            }
        }
    }

    private var actionTitle: LocalizedStringKey? {
        switch presentation.activity {
        case "created": "Opened"
        case "closed": "Closed"
        case "reopened": "Reopened"
        case "updated": "Updated"
        case "edited": "Edited"
        case "label_added": "Label added"
        case "label_removed": "Label removed"
        case "assigned": "Assigned"
        case "unassigned": "Unassigned"
        case "review_ready": "Ready for review"
        case "draft": "Draft"
        default: nil
        }
    }
}

struct MailboxThreadCard: View {
    let thread: MailboxThread
    let chats: [String: Chat]
    let expanded: Bool
    let busy: Bool
    let toggle: () -> Void
    let read: ([Int]) -> Void
    let open: (Chat) -> Void
    @State private var selected: Int?

    var body: some View {
        MailboxEventCard(item: thread.latest, target: thread.latest.chatId.flatMap { chats[$0] }, expanded: expanded, busy: busy,
            toggle: toggle, read: { read(thread.unreadIds) }, open: open,
            count: thread.items.count, threadUnread: !thread.unreadIds.isEmpty,
            history: thread.items.count > 1 ? AnyView(
                VStack(spacing: 0) {
                    ForEach(thread.items) { item in
                        MailboxEventCard(item: item, target: item.chatId.flatMap { chats[$0] }, expanded: selected == item.id, busy: busy,
                            toggle: { selected = selected == item.id ? nil : item.id }, read: { read([item.id]) }, open: open, compact: true)
                    }
                }.padding(.horizontal, 14).padding(.vertical, 8)
            ) : nil)
            .onChange(of: expanded) { _, _ in selected = nil }
    }
}
