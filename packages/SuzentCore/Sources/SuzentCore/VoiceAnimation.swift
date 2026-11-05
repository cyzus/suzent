import Foundation

public enum VoiceAnimation {
    public static var html: String {
        guard let url = Bundle.module.url(forResource: "voice-cube", withExtension: "html"),
              let html = try? String(contentsOf: url, encoding: .utf8) else { return "" }
        return html
    }
}
