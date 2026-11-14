import SwiftUI
import SuzentCore

struct DesktopSwatch: View {
    let desktop: SavedDesktop
    var size: CGFloat = 10
    var body: some View {
        Rectangle().fill(Color(presentation: desktop.color)).frame(width: size, height: size).accessibilityHidden(true)
    }
}

enum HomeTab: Hashable { case chats, inbox, settings }

/// Which conversation list fills the home sidebar.
enum HomeListMode: String { case recent, projects }

/// Compact-width home navigation. It lives in the stack's root view, so pushed pages cover it.
struct HomeTabBar: View {
    @Binding var selection: HomeTab
    var unread: Int = 0

    var body: some View {
        HStack(spacing: 0) {
            item(.chats, title: "Chats", icon: "bubble.left.and.bubble.right")
            item(.inbox, title: "Inbox", icon: "tray")
            item(.settings, title: "Settings", icon: "gearshape")
        }
        .dynamicTypeSize(...DynamicTypeSize.accessibility2)
        .background(Color.suzentSurface.ignoresSafeArea(edges: .bottom))
        .overlay(alignment: .top) {
            Rectangle().fill(Color.suzentOutline).frame(height: PresentationTokens.borderWidth)
        }
    }

    private func item(_ tab: HomeTab, title: LocalizedStringKey, icon: String) -> some View {
        let selected = selection == tab
        return Button { selection = tab } label: {
            VStack(spacing: 3) {
                // A fixed icon box keeps the filled and outline symbols from shifting the labels.
                Image(systemName: selected ? "\(icon).fill" : icon).font(.system(size: 19, weight: selected ? .semibold : .regular))
                    .frame(height: 24)
                    .overlay(alignment: .topTrailing) {
                        if tab == .inbox && unread > 0 {
                            Text(unread > 99 ? "99+" : String(unread)).font(.system(size: 9, weight: .bold))
                                .padding(3).background(Color.accentColor, in: Capsule()).foregroundStyle(.white).offset(x: 16, y: -5)
                        }
                    }
                Text(title).suzentFont(11, weight: selected ? .bold : .medium)
            }.foregroundStyle(selected ? Color.suzentText : Color.suzentMuted)
                .frame(maxWidth: .infinity, minHeight: 52).padding(.top, PresentationTokens.borderWidth)
                .overlay(alignment: .top) {
                    if selected { Rectangle().fill(Color.suzentText).frame(width: 32, height: 3).accessibilityHidden(true) }
                }
                .contentShape(Rectangle())
        }.buttonStyle(.plain)
            .accessibilityAddTraits(selected ? [.isSelected, .isButton] : .isButton)
    }
}

struct HomeListPicker: View {
    @Binding var selection: HomeListMode
    let modes: [HomeListMode]

    var body: some View {
        SuzentSegmentedTabs(options: modes, selection: $selection, title: title)
    }

    private func title(_ mode: HomeListMode) -> LocalizedStringKey {
        switch mode {
        case .recent: "Recent"
        case .projects: "Projects"
        }
    }
}

struct DesktopCard: View {
    let desktop: SavedDesktop
    let origin: String
    let count: Int

    var body: some View {
        HStack(spacing: 12) {
            // The same computer mark as the home screen's desktop line; colour swatches stay in the desktops list.
            Image(systemName: "desktopcomputer").font(.system(size: 17, weight: .medium))
                .frame(width: 38, height: 38)
                .background(Color.suzentTabTrack)
                .overlay(Rectangle().strokeBorder(Color.suzentOutline.opacity(0.3), lineWidth: 1))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(desktop.name).suzentFont(PresentationTokens.typeControl, weight: .semibold).lineLimit(1)
                Text("Connected · \(displayOrigin(origin))").font(.caption.monospaced()).foregroundStyle(Color.suzentMuted).lineLimit(1).truncationMode(.middle)
            }
            Spacer(minLength: 8)
            if count > 1 {
                Text("\(count) desktops").font(.caption).foregroundStyle(Color.suzentMuted)
            }
        }.padding(.vertical, 4)
    }
}

/// The scheme is noise in a narrow row and pushes the host and port out of view.
func displayOrigin(_ origin: String) -> String {
    var value = origin
    for scheme in ["https://", "http://"] where value.hasPrefix(scheme) { value.removeFirst(scheme.count) }
    return value.hasSuffix("/") ? String(value.dropLast()) : value
}

struct DesktopsPage: View {
    @Bindable var model: MobileModel
    let pairAnother: () -> Void
    @State private var forgetting: SavedDesktop?

    var body: some View {
        Form {
            Section {
                ForEach(model.desktops) { desktop in
                    row(desktop)
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            // Not role: .destructive, which would animate the row away before the confirmation.
                            Button { forgetting = desktop } label: { Label("Forget", systemImage: "trash") }
                                .tint(Color.suzentDanger)
                        }
                        .accessibilityActions {
                            Button("Forget") { forgetting = desktop }
                        }
                }
            } footer: {
                Text("Each desktop keeps its own conversations, access and Node pairing.").foregroundStyle(Color.suzentMuted)
            }
            Section {
                Button { model.beginPairing(repairActive: false); pairAnother() } label: {
                    Label("Pair another desktop", systemImage: "plus")
                }.disabled(model.busy || model.streaming || model.checkingDesktopId != nil)
            }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Color.suzentBackground)
        .navigationTitle("Desktops").navigationBarTitleDisplayMode(.inline)
        .alert("Forget this desktop?", isPresented: Binding(get: { forgetting != nil }, set: { if !$0 { forgetting = nil } }), presenting: forgetting) { desktop in
            Button("Cancel", role: .cancel) {}
            Button("Forget", role: .destructive) { model.forgetDesktop(desktop.id) }
        } message: { desktop in
            Text("This phone will need to pair again before it can reach \(desktop.name). To revoke access, also remove its credentials on the desktop.")
        }
    }

    private func row(_ desktop: SavedDesktop) -> some View {
        let active = desktop.id == model.activeDesktopId && model.connected
        let checking = model.checkingDesktopId == desktop.id
        return Button { if !active { Task { await model.switchDesktop(desktop.id) } } } label: {
            HStack(spacing: 12) {
                DesktopSwatch(desktop: desktop, size: 12)
                VStack(alignment: .leading, spacing: 2) {
                    Text(desktop.name).suzentFont(PresentationTokens.typeControl, weight: active ? .semibold : .regular)
                        .foregroundStyle(Color.suzentText).lineLimit(1)
                    Text(displayOrigin(desktop.connection.origin)).font(.caption.monospaced()).foregroundStyle(Color.suzentMuted)
                        .lineLimit(1).truncationMode(.middle)
                }
                Spacer(minLength: 8)
                if checking {
                    ProgressView().controlSize(.small)
                    Text("Checking…").font(.caption).foregroundStyle(Color.suzentMuted)
                } else if active {
                    Image(systemName: "checkmark").font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Color(presentation: PresentationTokens.blue))
                }
            }.frame(minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.plain)
            // Not disabled when active: a disabled row renders dimmed and reads as unavailable.
            .disabled(model.busy || model.checkingDesktopId != nil)
            .accessibilityAddTraits(active ? .isSelected : [])
    }
}
