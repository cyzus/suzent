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
                    Text(invitation.origin).font(.body.monospaced()).textSelection(.enabled)
                    Text("Your desktop will ask you to approve this phone. Node access stays separate.")
                    Button("Request pairing", action: model.approveDestination)
                        .buttonStyle(SuzentButtonStyle(prominent: true)).disabled(model.busy)
                    Button("Cancel", action: model.cancelPairing).disabled(model.busy)
                } else {
                    Text("On desktop, open Settings → Devices → Mobile access, then choose Pair a phone.")
                    Button("Scan desktop QR code", systemImage: "qrcode.viewfinder") { scanner = true }
                        .buttonStyle(SuzentButtonStyle(prominent: true)).disabled(model.busy)
                    DisclosureGroup("Paste an invitation instead") {
                        VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
                            TextField("Pairing invitation", text: $model.invitationText, axis: .vertical)
                                .textInputAutocapitalization(.never).autocorrectionDisabled().lineLimit(3...6)
                                .padding().overlay(Rectangle().stroke(.secondary))
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
        .sheet(isPresented: $scanner) { PairingScanner(onScan: model.stageInvitation) }
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
            Text("Manage or revoke access in desktop Settings → Devices → Mobile access.")
                .font(.footnote).foregroundStyle(.secondary)
            Text("Tool approvals remain on your desktop. Node access is separate.")
                .font(.footnote).foregroundStyle(.secondary)
        }
    }
    private func permission(_ title: LocalizedStringKey, enabled: Bool) -> some View {
        HStack { Text(title); Spacer(); Text(enabled ? String(localized: "Allowed") : String(localized: "Not allowed")).foregroundStyle(.secondary) }
    }
}
