import SwiftUI
import SuzentCore

/// The desktop's unread count: a yellow block with black figures, used by the tab bar and the filters.
struct SuzentCountBadge: View {
    let count: Int

    var body: some View {
        Text(count > 99 ? "99+" : String(count)).font(.system(size: 10, weight: .bold, design: .monospaced))
            .foregroundStyle(Color.black).padding(.horizontal, 4).frame(minHeight: 15)
            .background(Color.suzentYellow).overlay(Rectangle().strokeBorder(Color.black, lineWidth: 1))
            .fixedSize()
    }
}

/// What sent an inbox thread: a kind icon, or the source's initials.
struct MailboxSourceMark: View {
    let item: MailboxItem
    var size: CGFloat = 32

    var body: some View {
        let muted = item.status == "unrouted"
        Group {
            if let icon { Image(systemName: icon).font(.system(size: size * 0.45, weight: .medium)) }
            else {
                Text(String(item.source.filter { $0.isLetter || $0.isNumber }.prefix(2)).uppercased().ifEmpty("?"))
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
            }
        }
        .foregroundStyle(muted ? Color.suzentMuted : Color.suzentText)
        .frame(width: size, height: size)
        .background(Color.suzentSurface)
        .overlay(Rectangle().strokeBorder(muted ? Color.suzentRowDivider : Color.suzentOutline, lineWidth: 1))
        .accessibilityHidden(true)
    }

    private var icon: String? {
        switch item.sourceKind {
        case "schedule": "clock"
        case "agent_inbox": "bubble.left.and.bubble.right"
        case "peer": "desktopcomputer"
        case "email": "envelope"
        default: item.display.icon == "code" ? "arrow.triangle.branch" : nil
        }
    }
}

/// Where an inbox event went, styled by what happened to it.
struct MailboxStatusPill: View {
    let status: String
    let target: Chat?

    var body: some View {
        HStack(spacing: 4) {
            if let icon { Image(systemName: icon).font(.system(size: 9, weight: .semibold)) }
            label.lineLimit(1)
        }
        .suzentFont(10, design: .monospaced)
        .foregroundStyle(tint)
        .padding(.horizontal, 6).frame(minHeight: 20)
        .background(status == "routed" || status == "unrouted" ? Color.clear : tint.opacity(0.08))
        .overlay {
            if status == "unrouted" { Rectangle().strokeBorder(tint.opacity(0.6), style: StrokeStyle(lineWidth: 1, dash: [3, 2])) }
            else { Rectangle().strokeBorder(status == "routed" ? Color.suzentRowDivider : tint.opacity(0.6), lineWidth: 1) }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private var label: Text {
        switch status {
        case "error": Text("Error")
        case "queued": Text("Queued")
        case "notified": Text("Notified")
        case "unrouted": Text("Unrouted")
        default: target.flatMap { $0.title.isEmpty ? nil : Text($0.title) } ?? Text("Delivered")
        }
    }

    private var icon: String? {
        switch status {
        case "error": "exclamationmark.triangle"
        case "queued": "tray.full"
        case "notified": "bell"
        case "routed": "arrow.turn.down.right"
        default: nil
        }
    }

    private var tint: Color {
        switch status {
        case "error": .suzentDanger
        case "queued": .suzentWarning
        case "notified": .suzentInfo
        case "routed": .suzentText
        default: .suzentMuted
        }
    }
}

struct MailboxThreadRow: View {
    let thread: MailboxThread
    let target: Chat?

    var body: some View {
        let latest = thread.latest
        let unread = !thread.unreadIds.isEmpty
        HStack(alignment: .top, spacing: 12) {
            MailboxSourceMark(item: latest)
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 7) {
                    if unread {
                        Rectangle().fill(Color.suzentYellow).frame(width: 7, height: 7)
                            .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: 1)).alignmentGuide(.firstTextBaseline) { $0[.bottom] - 1 }
                            .accessibilityLabel("Unread")
                    }
                    Text(latest.display.title).suzentFont(14, weight: unread ? .semibold : .regular).lineSpacing(2)
                        .foregroundStyle(latest.status == "unrouted" ? Color.suzentMuted : Color.suzentText)
                        .lineLimit(2).multilineTextAlignment(.leading)
                }
                HStack(spacing: 8) {
                    Text(meta).suzentFont(11, design: .monospaced).foregroundStyle(Color.suzentMuted).lineLimit(1)
                    Spacer(minLength: 4)
                    MailboxStatusPill(status: latest.status, target: target)
                }
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
        .overlay(alignment: .bottom) { Rectangle().fill(Color.suzentRowDivider).frame(height: 1) }
    }

    private var meta: String {
        let latest = thread.latest
        var parts = [latest.display.context ?? latest.display.source]
        if thread.items.count > 1 { parts.append("×\(thread.items.count)") }
        if let date = suzentParseDate(latest.createdAt) { parts.append(date.suzentStamp) }
        return parts.joined(separator: " · ")
    }
}

/// One inbox thread on its own page: what it is, where it went, its history and the latest raw event.
struct MailboxThreadDetail: View {
    @Bindable var model: MobileModel
    let key: String
    let openChat: (Chat) -> Void

    var body: some View {
        Group {
            if let thread = mailboxThreads(model.mailbox.items).first(where: { $0.id == key }) { content(thread) }
            else { ContentUnavailableView("Event unavailable", systemImage: "tray") }
        }
        .background(Color.suzentSurface)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: key) {
            let unread = mailboxThreads(model.mailbox.items).first { $0.id == key }?.unreadIds ?? []
            if !unread.isEmpty { await model.readMailbox(unread) }
        }
    }

    private func content(_ thread: MailboxThread) -> some View {
        let latest = thread.latest
        let target = latest.chatId.flatMap { model.mailboxChats[$0] }
        return ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 12) {
                    MailboxSourceMark(item: latest, size: 36)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(latest.display.source).suzentFont(12, weight: .semibold)
                        if let context = latest.display.context {
                            Text(context).suzentFont(11, design: .monospaced).foregroundStyle(Color.suzentMuted).lineLimit(1)
                        }
                    }
                }
                Text(latest.display.title).suzentFont(18, weight: .semibold).lineSpacing(3).foregroundStyle(Color.suzentText)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 16).textSelection(.enabled)
                HStack(spacing: 8) {
                    MailboxStatusPill(status: latest.status, target: target)
                    if let date = suzentParseDate(latest.createdAt) {
                        Text(date.suzentStamp).suzentFont(11, design: .monospaced).foregroundStyle(Color.suzentMuted)
                    }
                }.padding(.top, 10)
                if latest.chatId != nil {
                    section(Text("Related conversation"))
                    conversation(target)
                }
                if thread.items.count > 1 {
                    section(Text("Activity · \(thread.items.count)"))
                    VStack(spacing: 0) {
                        ForEach(Array(thread.items.enumerated()), id: \.element.id) { index, item in timelineRow(item, first: index == 0) }
                    }
                }
                if !latest.payload.isEmpty {
                    section(Text("Original content"))
                    ScrollView {
                        Text(latest.payload).font(.system(size: 12, design: .monospaced)).lineSpacing(3)
                            .foregroundStyle(Color(presentation: PresentationTokens.text_dark)).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(12)
                    }.frame(maxHeight: 240).fixedSize(horizontal: false, vertical: true)
                        .background(Color(presentation: PresentationTokens.background_dark))
                        .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: 1))
                    Text(latest.eventType).suzentFont(10, design: .monospaced).foregroundStyle(Color.suzentMuted).padding(.top, 6)
                }
            }.padding(16).padding(.bottom, 24)
        }
    }

    /// The related conversation, drawn like a row in the conversation list.
    private func conversation(_ target: Chat?) -> some View {
        Button { if let target { openChat(target) } } label: {
            HStack(spacing: 6) {
                VStack(alignment: .leading, spacing: 0) {
                    Text(target.flatMap { $0.title.isEmpty ? nil : $0.title } ?? String(localized: "Conversation unavailable"))
                        .suzentFont(PresentationTokens.typeCaption, weight: .medium).lineLimit(1).truncationMode(.tail)
                        .opacity(target == nil ? 0.6 : 1)
                    if let project = target?.projectName, !project.isEmpty {
                        Text(project).suzentFont(PresentationTokens.typeSidebarSection, weight: .medium)
                            .foregroundStyle(Color.suzentMuted).lineLimit(1).frame(minHeight: 16)
                    }
                }
                Spacer(minLength: 0)
                if target?.isRunning == true { Image(systemName: "ellipsis") }
            }.padding(.vertical, PresentationTokens.spaceRow)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(ChatRowButtonStyle(selected: false, divider: true)).disabled(target == nil)
    }

    private func section(_ title: Text) -> some View {
        title.suzentFont(11, design: .monospaced).foregroundStyle(Color.suzentMuted).padding(.top, 24).padding(.bottom, 8)
    }

    private func timelineRow(_ item: MailboxItem, first: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Rectangle().fill(first ? Color.suzentText : Color.suzentMuted.opacity(0.5)).frame(width: 6, height: 6)
            mailboxActivityText(item).suzentFont(13, weight: item.unread ? .semibold : .regular).foregroundStyle(Color.suzentText)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let date = suzentParseDate(item.createdAt) {
                Text(date.suzentStamp).suzentFont(11, design: .monospaced).foregroundStyle(Color.suzentMuted)
            }
        }.padding(.vertical, 8)
            .overlay(alignment: .bottom) { Rectangle().fill(Color.suzentRowDivider.opacity(0.6)).frame(height: 1) }
    }
}

/// A thread step: its activity, and the label or detail it touched; plain events fall back to their title.
func mailboxActivityText(_ item: MailboxItem) -> Text {
    let presentation = item.display
    let action: Text? = switch presentation.activity {
    case "created": Text("Opened")
    case "closed": Text("Closed")
    case "reopened": Text("Reopened")
    case "updated": Text("Updated")
    case "edited": Text("Edited")
    case "label_added": Text("Label added")
    case "label_removed": Text("Label removed")
    case "assigned": Text("Assigned")
    case "unassigned": Text("Unassigned")
    case "review_ready": Text("Ready for review")
    case "draft": Text("Draft")
    default: nil
    }
    guard let action else { return Text(presentation.title) }
    guard let detail = presentation.detail else { return action }
    return action + Text(" · \(detail)")
}

private extension String {
    func ifEmpty(_ fallback: String) -> String { isEmpty ? fallback : self }
}
