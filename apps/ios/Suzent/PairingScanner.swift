import SwiftUI
import AVFoundation
import VisionKit

struct PairingScanner: View {
    let onScan: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var allowed: Bool?
    @State private var failed = false

    var body: some View {
        NavigationStack {
            Group {
                if allowed == true, DataScannerViewController.isSupported, !failed {
                    ScannerController(onScan: { value in onScan(value); dismiss() }, onFailure: { failed = true })
                } else if allowed == nil { ProgressView() }
                else {
                    ContentUnavailableView("Camera unavailable", systemImage: "camera",
                        description: Text("Allow camera access in Settings, or paste the pairing invitation from your desktop."))
                }
            }
            .navigationTitle("Scan pairing code")
            .toolbar { Button("Cancel") { dismiss() } }
            .task { allowed = await AVCaptureDevice.requestAccess(for: .video) }
        }
    }
}

private struct ScannerController: UIViewControllerRepresentable {
    let onScan: (String) -> Void
    let onFailure: () -> Void

    func makeUIViewController(context: Context) -> Controller {
        Controller(onScan: onScan, onFailure: onFailure)
    }
    func updateUIViewController(_ controller: Controller, context: Context) {}

    final class Controller: UIViewController, DataScannerViewControllerDelegate {
        private let scanner = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])],
            qualityLevel: .balanced, recognizesMultipleItems: false, isHighlightingEnabled: true)
        private let onScan: (String) -> Void
        private let onFailure: () -> Void
        private var delivered = false

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
            guard !delivered else { return }
            for item in addedItems {
                if case .barcode(let barcode) = item, let value = barcode.payloadStringValue {
                    delivered = true
                    scanner.stopScanning()
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
