import SwiftUI
import SuzentCore

struct PairingView: View {
    @Bindable var model: MobileModel
    @State private var scanner = false
    @State private var pasting = false
    @ScaledMetric(relativeTo: .title2) private var titleSize = PresentationTokens.typeTitle
    @ScaledMetric(relativeTo: .body) private var bodySize = PresentationTokens.typeBody

    var body: some View {
        Group {
            if model.pairingCode == nil && model.pairingInvitation == nil && !model.busy { welcome } else { progress }
        }
        .font(.system(size: bodySize))
        .fullScreenCover(isPresented: $scanner) { PairingScanner(model: model) }
    }

    private var welcome: some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: PresentationTokens.spaceLarge)
                    GreetingCube(engaged: false).frame(width: 168, height: 168)
                    Text("Your Suzent, together.").font(.system(size: titleSize, weight: .bold))
                        .padding(.top, PresentationTokens.spaceLarge)
                    Text("Connect to your desktop. Continue conversations wherever you are.")
                        .foregroundStyle(Color.suzentMuted).padding(.top, PresentationTokens.spaceSmall)
                    Spacer(minLength: PresentationTokens.spaceLarge)
                    Button("Scan desktop QR code", systemImage: "qrcode.viewfinder") { scanner = true }
                        .buttonStyle(SuzentButtonStyle(prominent: true))
                    Text("On desktop: Settings → Devices → Mobile access")
                        .suzentFont(PresentationTokens.typeCaption).foregroundStyle(Color.suzentMuted)
                        .padding(.top, PresentationTokens.spaceMedium)
                    HStack(spacing: PresentationTokens.spaceSmall) {
                        Button("Paste an invitation instead") { pasting = true }
                        Text(verbatim: "·").foregroundStyle(Color.suzentMuted).accessibilityHidden(true)
                        Button("Try offline demo") { Task { await model.startDemo() } }
                    }
                    .suzentFont(PresentationTokens.typeCaption, weight: .medium).buttonStyle(.plain)
                    .frame(minHeight: PresentationTokens.controlHeight).padding(.top, PresentationTokens.spaceSmall)
                }
                .multilineTextAlignment(.center)
                .padding(.horizontal, PresentationTokens.spaceLarge).padding(.bottom, PresentationTokens.spaceSmall)
                .frame(maxWidth: 480).frame(maxWidth: .infinity, minHeight: proxy.size.height)
            }.scrollBounceBehavior(.basedOnSize)
        }
        .sheet(isPresented: $pasting) {
            VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
                Text("Pairing invitation").suzentFont(PresentationTokens.typeSection, weight: .bold)
                SuzentTextInput(placeholder: "Pairing invitation", text: $model.invitationText, multiline: true)
                Button("Review invitation") { pasting = false; model.stageInvitation(model.invitationText) }
                    .buttonStyle(SuzentButtonStyle(prominent: true)).disabled(model.invitationText.isEmpty)
                Spacer(minLength: 0)
            }
            .padding(PresentationTokens.spacePage).padding(.top, PresentationTokens.spaceSmall)
            .presentationDetents([.height(280), .large])
            .presentationDragIndicator(.visible)
            .presentationCornerRadius(PresentationTokens.radius)
            .presentationBackground(Color.suzentSurface)
        }
    }

    private var progress: some View {
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
                    if model.busy { ProgressView(model.pairingStatus ?? String(localized: "Finishing connection…")) }
                    Button(invitation.phoneConfirmation ? String(localized: "Confirm connection") : String(localized: "Request pairing"), action: model.approveDestination)
                        .buttonStyle(SuzentButtonStyle(prominent: true)).disabled(model.busy)
                    Button("Cancel", action: model.cancelPairing).disabled(model.busy)
                } else {
                    ProgressView(model.pairingStatus ?? String(localized: "Checking desktop addresses…"))
                    Button("Cancel pairing", action: model.cancelPairing).buttonStyle(SuzentButtonStyle())
                }
            }.padding(PresentationTokens.spacePage)
        }
    }
}

struct ClientPermissionsView: View {
    let device: ClientDevice
    let origin: String

    var body: some View {
        VStack(alignment: .leading, spacing: PresentationTokens.spaceMedium) {
            Text(device.displayName).font(.headline)
            Text(origin).font(.caption.monospaced()).foregroundStyle(Color.suzentMuted)
            Label(device.permissions.allChats ? String(localized: "All conversations")
                : String(localized: "Shared conversations: \(device.permissions.chatIds.count)"), systemImage: "text.bubble")
            if device.permissions.allChats { Text("Regent can coordinate work across all your projects.").font(.footnote).foregroundStyle(Color.suzentMuted) }
            permission("Create conversations", enabled: device.permissions.createChats)
            permission("Manage conversations", enabled: device.permissions.manageChats == true)
            permission("Send messages", enabled: device.permissions.send)
            permission("Stop responses", enabled: device.permissions.stop)
            permission("Approve tool requests", enabled: device.permissions.approveTools == true)
            Text("Manage or revoke access in desktop Settings → Devices → Mobile access.")
                .font(.footnote).foregroundStyle(Color.suzentMuted)
            Text("Tool requests follow the conversation policy. Node access is separate.")
                .font(.footnote).foregroundStyle(Color.suzentMuted)
        }
    }
    private func permission(_ title: LocalizedStringKey, enabled: Bool) -> some View {
        HStack { Text(title); Spacer(); Text(enabled ? String(localized: "Allowed") : String(localized: "Not allowed")).foregroundStyle(Color.suzentMuted) }
    }
}


struct PairingPermissionsView: View {
    let permissions: ClientPermissions
    var body: some View {
        VStack(alignment: .leading, spacing: PresentationTokens.spaceSmall) {
            permission("Manage conversations", enabled: permissions.manageChats == true)
            if permissions.allChats && permissions.createChats && permissions.manageChats == true && permissions.send && permissions.stop && permissions.approveTools == true {
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
            if permissions.allChats { Text("Regent can coordinate work across all your projects.").font(.footnote).foregroundStyle(Color.suzentMuted) }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
            .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: PresentationTokens.borderWidth))
    }
    private func permission(_ title: LocalizedStringKey, enabled: Bool) -> some View {
        HStack { Text(title); Spacer(); Text(enabled ? String(localized: "Allowed") : String(localized: "Not allowed")) }
    }
}
