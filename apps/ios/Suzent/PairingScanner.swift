import SwiftUI
import AVFoundation
import VisionKit
import SuzentCore

struct PairingScanner: View {
    @Bindable var model: MobileModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var allowed: Bool?
    @State private var failed = false
    @State private var torch = false
    @State private var paste = false
    private var found: Bool { model.pairingInvitation != nil || model.pairingCode != nil }
    private var scanning: Bool { !found && !model.busy && model.error == nil && !paste }
    private func reset() { model.cancelPairing(); model.error = nil }
    private func setTorch(_ enabled: Bool) {
        guard let device = AVCaptureDevice.default(for: .video), device.hasTorch else { return }
        do { try device.lockForConfiguration(); device.torchMode = enabled ? .on : .off; device.unlockForConfiguration(); torch = enabled }
        catch { torch = false }
    }
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Color.black.ignoresSafeArea()
                if allowed == true, DataScannerViewController.isSupported, !failed {
                    ScannerController(active: scanning && scenePhase == .active, onScan: model.stageInvitation, onFailure: { failed = true }).ignoresSafeArea()
                }
                LinearGradient(colors: [.black.opacity(0.75), .clear, .black.opacity(0.8)], startPoint: .top, endPoint: .bottom).ignoresSafeArea().allowsHitTesting(false)
                VStack {
                    HStack { SuzentWordmark(); Spacer(); Button { reset(); dismiss() } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }.accessibilityLabel("Cancel") }
                    VStack(spacing: 8) {
                        Text("Connect your desktop").font(.title2.bold())
                        Text("Place the pairing code inside the frame").font(.subheadline)
                    }.padding(.top, 24)
                    Spacer()
                }.padding(.horizontal, 24).foregroundStyle(.white)
                if allowed == true && !failed {
                    ScanFrame(active: scanning, found: found)
                        .frame(width: geometry.size.width * 0.76, height: min(geometry.size.width * 0.76, geometry.size.height * 0.38))
                        .offset(y: found ? -65 : -20).allowsHitTesting(false)
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "camera").font(.largeTitle)
                        Text("Camera unavailable").font(.headline)
                        Text("Allow camera access in Settings, or paste the pairing invitation from your desktop.").font(.subheadline).multilineTextAlignment(.center)
                    }.foregroundStyle(.white).padding(32)
                }
                VStack { Spacer()
                    if found {
                        confirmation.transition(.move(edge: .bottom).combined(with: .opacity))
                    } else {
                        VStack(spacing: 18) {
                            if let error = model.error {
                                HStack {
                                    Text(error).font(.footnote).foregroundStyle(.primary)
                                    Spacer()
                                    Button("Scan again", action: reset).font(.footnote.bold())
                                }.padding(16).background(Color(uiColor: .systemBackground))
                                    .overlay(alignment: .leading) { Rectangle().fill(Color(presentation: PresentationTokens.yellow)).frame(width: 3) }
                                    .transition(.offset(y: 12).combined(with: .opacity))
                            } else if model.busy { ProgressView("Checking desktop addresses…").tint(.white).foregroundStyle(.white) }
                            HStack(spacing: 12) {
                                Button { setTorch(!torch) } label: { Image(systemName: torch ? "flashlight.on.fill" : "flashlight.off.fill").frame(width: 44, height: 44) }
                                    .foregroundStyle(torch ? .black : .white).background(torch ? Color(presentation: PresentationTokens.yellow) : .black.opacity(0.6))
                                    .accessibilityLabel("Flashlight").disabled(allowed != true || failed)
                                Button("Paste an invitation instead") { paste = true }.buttonStyle(SuzentButtonStyle(compact: true))
                            }
                            Text("On desktop, open Settings → Devices → Mobile access, then choose Pair a phone.").font(.caption).foregroundStyle(.white.opacity(0.8)).multilineTextAlignment(.center)
                        }.padding(24)
                    }
                }
            }.animation(reduceMotion ? nil : .spring(response: 0.5, dampingFraction: 0.9), value: found)
                .animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: model.error)
        }
        .task { allowed = await AVCaptureDevice.requestAccess(for: .video) }
        .onChange(of: model.pairingVersion) { _, _ in dismiss() }
        .onChange(of: scenePhase) { _, phase in if phase != .active { setTorch(false) } }
        .onDisappear { setTorch(false) }
        .sheet(isPresented: $paste) {
            VStack(spacing: 20) {
                Text("Paste an invitation instead").font(.headline)
                TextField("Pairing invitation", text: $model.invitationText, axis: .vertical).lineLimit(3...6).textInputAutocapitalization(.never).autocorrectionDisabled().padding().border(.secondary)
                Button("Review invitation") { paste = false; model.stageInvitation(model.invitationText) }.buttonStyle(SuzentButtonStyle(prominent: true)).disabled(model.busy || model.invitationText.isEmpty)
            }.padding(24).presentationDetents([.medium])
        }
    }
    private var confirmation: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack { Text("Desktop recognized").font(.caption.monospaced().bold()); Spacer(); Button("Scan again", action: reset).font(.caption) }
                HStack(spacing: 12) { SuzentLogoMark().frame(width: 42, height: 42)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(model.pairingPreview?.desktopName ?? String(localized: "Connect to this desktop?")).font(.headline)
                        Text(model.pairingInvitation?.origin ?? "").font(.caption.monospaced()).foregroundStyle(.secondary)
                    }
                }
                if let code = model.pairingCode { Text("Waiting for desktop approval"); Text(code).font(.title.monospaced().bold()) }
                else if let invitation = model.pairingInvitation {
                    if let preview = model.pairingPreview { DisclosureGroup("Desktop access") { PairingPermissionsView(permissions: preview.permissions) } }
                    Text(invitation.phoneConfirmation ? String(localized: "Confirm to connect with the permissions shown above. You do not need to approve again on desktop.") : String(localized: "Your desktop will ask you to approve this phone. Node access stays separate.")).font(.footnote).foregroundStyle(.secondary)
                    if let error = model.error { Text(error).font(.footnote).foregroundStyle(.red) }
                    if model.busy { ProgressView() }
                    Button(invitation.phoneConfirmation ? String(localized: "Confirm connection") : String(localized: "Request pairing"), action: model.approveDestination).buttonStyle(SuzentButtonStyle(prominent: true)).disabled(model.busy)
                }
            }.padding(24)
        }.frame(maxHeight: 340).background(Color(uiColor: .systemBackground))
            .overlay(alignment: .top) { Rectangle().fill(Color.primary).frame(height: 2) }
    }
}

private struct ScanFrame: View {
    let active: Bool
    let found: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !active || reduceMotion)) { timeline in
            Canvas { context, size in
                let length: CGFloat = found ? 34 : 26
                for (x, y, dx, dy) in [(0.0, 0.0, 1.0, 1.0), (size.width, 0.0, -1.0, 1.0), (0.0, size.height, 1.0, -1.0), (size.width, size.height, -1.0, -1.0)] {
                    var path = Path(); path.move(to: CGPoint(x: x, y: y + dy * length)); path.addLine(to: CGPoint(x: x, y: y)); path.addLine(to: CGPoint(x: x + dx * length, y: y))
                    context.stroke(path, with: .color(found ? .green : .white), lineWidth: 3)
                }
                if active {
                    let fraction = reduceMotion ? 0.5 : (sin(timeline.date.timeIntervalSinceReferenceDate * 1.6) + 1) / 2
                    let y = 20 + fraction * max(0, size.height - 40)
                    context.fill(Path(CGRect(x: 12, y: y, width: size.width - 24, height: 1)), with: .color(Color(presentation: PresentationTokens.blue)))
                }
            }
        }.accessibilityHidden(true)
    }
}

private struct ScannerController: UIViewControllerRepresentable {
    let active: Bool
    let onScan: (String) -> Void
    let onFailure: () -> Void

    func makeUIViewController(context: Context) -> Controller {
        Controller(onScan: onScan, onFailure: onFailure)
    }
    func updateUIViewController(_ controller: Controller, context: Context) { controller.setActive(active) }

    final class Controller: UIViewController, DataScannerViewControllerDelegate {
        private let scanner = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])],
            qualityLevel: .balanced, recognizesMultipleItems: false, isHighlightingEnabled: false)
        private let onScan: (String) -> Void
        private let onFailure: () -> Void
        private var delivered = false
        private var active = true
        func setActive(_ value: Bool) {
            active = value
            if value { delivered = false }
        }

        init(onScan: @escaping (String) -> Void, onFailure: @escaping () -> Void) {
            self.onScan = onScan
            self.onFailure = onFailure
            super.init(nibName: nil, bundle: nil)
        }
        required init?(coder: NSCoder) { nil }
        override func viewDidLoad() {
            super.viewDidLoad()
            scanner.delegate = self
            addChild(scanner)
            view.addSubview(scanner.view)
            scanner.view.frame = view.bounds
            scanner.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
            scanner.didMove(toParent: self)
        }
        override func viewDidAppear(_ animated: Bool) {
            super.viewDidAppear(animated)
            do { try scanner.startScanning() }
            catch { onFailure() }
        }
        override func viewWillDisappear(_ animated: Bool) {
            scanner.stopScanning()
            super.viewWillDisappear(animated)
        }
        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            guard active, !delivered else { return }
            for item in addedItems {
                if case .barcode(let barcode) = item, let value = barcode.payloadStringValue {
                    delivered = true
                    onScan(value)
                    return
                }
            }
        }
        func dataScanner(_ dataScanner: DataScannerViewController, becameUnavailableWithError error: DataScannerViewController.ScanningUnavailable) {
            onFailure()
        }
    }
}
