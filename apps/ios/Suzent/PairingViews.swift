import SwiftUI
import SuzentCore

struct PairingView: View {
    @Bindable var model: MobileModel
    @State private var scanner = false
    @ScaledMetric(relativeTo: .title2) private var titleSize = PresentationTokens.typeTitle
    @ScaledMetric(relativeTo: .body) private var bodySize = PresentationTokens.typeBody

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: PresentationTokens.spaceLarge) {
                VStack(alignment: .leading, spacing: PresentationTokens.spaceSmall) {
                    Text("Your Suzent, together.").font(.system(size: titleSize, weight: .bold))
                    Text("Connect to your desktop. Continue conversations wherever you are.")
                }
                .padding(PresentationTokens.spaceLarge)
                .foregroundStyle(.black)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(presentation: PresentationTokens.yellow))
                .overlay(Rectangle().stroke(.black, lineWidth: PresentationTokens.borderWidth))

                if let code = model.pairingCode {
                    ProgressView("Waiting for desktop approval")
                    Text(code).font(.system(.largeTitle, design: .monospaced).bold()).textSelection(.enabled)
                    Text("Check this code on your desktop, then choose which conversations and actions to share.")
                    Button("Cancel pairing", action: model.cancelPairing).buttonStyle(SuzentButtonStyle())
                } else if let invitation = model.pairingInvitation {
                    Text("Connect to this desktop?").font(.title2.bold())
                    if let preview = model.pairingPreview {
                        Text(preview.desktopName).font(.title2.bold())
                        PairingPermissionsView(permissions: preview.permissions)
                    }
                    Text(invitation.origin).font(.body.monospaced()).textSelection(.enabled)
                    Text(invitation.phoneConfirmation
                         ? String(localized: "Confirm to connect with the permissions shown above. You do not need to approve again on desktop.")
                         : String(localized: "Your desktop will ask you to approve this phone. Node access stays separate."))
                    if model.busy { ProgressView() }
                    Button(invitation.phoneConfirmation ? String(localized: "Confirm connection") : String(localized: "Request pairing"), action: model.approveDestination)
                        .buttonStyle(SuzentButtonStyle(prominent: true)).disabled(model.busy)
                    Button("Cancel", action: model.cancelPairing).disabled(model.busy)
                } else if model.busy {
                    ProgressView("Checking desktop addresses…")
                    Button("Cancel pairing", action: model.cancelPairing).buttonStyle(SuzentButtonStyle())
                } else {
                    Text("On desktop, open Settings → Devices → Mobile access, then choose Pair a phone.")
                    Button("Scan desktop QR code", systemImage: "qrcode.viewfinder") { scanner = true }
                        .buttonStyle(SuzentButtonStyle(prominent: true)).disabled(model.busy)
                    DisclosureGroup("Paste an invitation instead") {
                        VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
                            SuzentTextInput(placeholder: "Pairing invitation", text: $model.invitationText, multiline: true)
                            Button("Review invitation") { model.stageInvitation(model.invitationText) }
                                .buttonStyle(SuzentButtonStyle()).disabled(model.busy || model.invitationText.isEmpty)
                        }.padding(.top)
                    }
                    if model.canReconnect {
                        Divider()
                        Text(model.origin).font(.caption).foregroundStyle(.secondary)
                        Button("Reconnect to desktop") { Task { await model.connect() } }
                            .buttonStyle(SuzentButtonStyle()).disabled(model.busy)
                    }
                }
            }.padding(PresentationTokens.spacePage)
        }
        .font(.system(size: bodySize))
        .fullScreenCover(isPresented: $scanner) { PairingScanner(model: model) }
    }
}

struct ClientPermissionsView: View {
    let device: ClientDevice
    let origin: String

    var body: some View {
        VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
            Text(device.displayName).font(.headline)
            Text(origin).font(.caption.monospaced()).foregroundStyle(.secondary)
            Label(device.permissions.allChats ? String(localized: "All conversations")
                : String(localized: "Shared conversations: \(device.permissions.chatIds.count)"), systemImage: "text.bubble")
            permission("Create conversations", enabled: device.permissions.createChats)
            permission("Send messages", enabled: device.permissions.send)
            permission("Stop responses", enabled: device.permissions.stop)
            permission("Approve tool requests", enabled: device.permissions.approveTools == true)
            Text("Manage or revoke access in desktop Settings → Devices → Mobile access.")
                .font(.footnote).foregroundStyle(.secondary)
            Text("Tool requests follow the conversation policy. Node access is separate.")
                .font(.footnote).foregroundStyle(.secondary)
        }
    }
    private func permission(_ title: LocalizedStringKey, enabled: Bool) -> some View {
        HStack { Text(title); Spacer(); Text(enabled ? String(localized: "Allowed") : String(localized: "Not allowed")).foregroundStyle(.secondary) }
    }
}


struct PairingPermissionsView: View {
    let permissions: ClientPermissions
    var body: some View {
        VStack(alignment: .leading, spacing: PresentationTokens.spaceSmall) {
            if permissions.allChats && permissions.createChats && permissions.send && permissions.stop && permissions.approveTools == true {
                Text("Full access").font(.headline)
                Text("All conversations, messaging, and tool approvals.").font(.subheadline)
            } else {
            Text(permissions.allChats ? String(localized: "All conversations")
                 : String(localized: "Shared conversations: \(permissions.chatIds.count)"))
            permission("Create conversations", enabled: permissions.createChats)
            permission("Send messages", enabled: permissions.send)
            permission("Stop responses", enabled: permissions.stop)
            permission("Approve tool requests", enabled: permissions.approveTools == true)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
            .overlay(Rectangle().stroke(.primary, lineWidth: PresentationTokens.borderWidth))
    }
    private func permission(_ title: LocalizedStringKey, enabled: Bool) -> some View {
        HStack { Text(title); Spacer(); Text(enabled ? String(localized: "Allowed") : String(localized: "Not allowed")) }
    }
}
