import SwiftUI
import WebKit
import SuzentCore

struct VoiceCubeView: UIViewRepresentable {
    let voice: VoiceSession
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reducedMotion

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.isOpaque = false
        view.backgroundColor = .clear
        view.scrollView.isScrollEnabled = false
        view.isUserInteractionEnabled = false
        view.accessibilityElementsHidden = true
        view.navigationDelegate = context.coordinator
        view.loadHTMLString(VoiceAnimation.html, baseURL: nil)
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        let state: [String: Any] = ["status": voice.animationState, "working": voice.working,
                                    "level": voice.micLevel, "dark": colorScheme == .dark,
                                    "reducedMotion": reducedMotion]
        guard let data = try? JSONSerialization.data(withJSONObject: state),
              let json = String(data: data, encoding: .utf8) else { return }
        context.coordinator.script = "window.updateVoiceCube?.(\(json))"
        context.coordinator.update(view)
    }

    static func dismantleUIView(_ view: WKWebView, coordinator: Coordinator) {
        view.evaluateJavaScript("window.dispatchEvent(new Event('pagehide'))", completionHandler: nil)
        view.stopLoading()
        view.navigationDelegate = nil
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var script = ""
        private var loaded = false
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            loaded = true
            update(webView)
        }
        func update(_ view: WKWebView) {
            if loaded { view.evaluateJavaScript(script, completionHandler: nil) }
        }
    }
}
