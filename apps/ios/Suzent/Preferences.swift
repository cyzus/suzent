import SwiftUI
import SuzentCore

/// Phone-only display preferences; nothing here reaches the desktop.
enum AppearancePreference: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .light: .light
        case .dark: .dark
        }
    }

    var title: LocalizedStringKey {
        switch self {
        case .system: "Match system"
        case .light: "Light"
        case .dark: "Dark"
        }
    }
}

enum TextSizePreference: String, CaseIterable, Identifiable {
    case system, small, standard, large, extraLarge
    var id: String { rawValue }

    /// Nil keeps following the system Dynamic Type setting.
    var dynamicTypeSize: DynamicTypeSize? {
        switch self {
        case .system: nil
        case .small: .small
        case .standard: .large
        case .large: .xLarge
        case .extraLarge: .xxLarge
        }
    }

    var title: LocalizedStringKey {
        switch self {
        case .system: "Match system"
        case .small: "Small"
        case .standard: "Default"
        case .large: "Large"
        case .extraLarge: "Extra large"
        }
    }
}

enum StoredPreference {
    static let appearance = "appearance"
    static let textSize = "textSize"
    static let haptics = "haptics"
}

private struct AppPreferences: ViewModifier {
    @AppStorage(StoredPreference.appearance) private var appearance: AppearancePreference = .system
    @AppStorage(StoredPreference.textSize) private var textSize: TextSizePreference = .system

    func body(content: Content) -> some View {
        if let size = textSize.dynamicTypeSize {
            content.preferredColorScheme(appearance.colorScheme).dynamicTypeSize(size)
        } else {
            content.preferredColorScheme(appearance.colorScheme)
        }
    }
}

private struct OptionalFeedback<Trigger: Equatable>: ViewModifier {
    @AppStorage(StoredPreference.haptics) private var haptics = true
    let trigger: Trigger
    let feedback: (Trigger, Trigger) -> SensoryFeedback?

    func body(content: Content) -> some View {
        content.sensoryFeedback(trigger: trigger) { old, new in haptics ? feedback(old, new) : nil }
    }
}

extension View {
    func appPreferences() -> some View { modifier(AppPreferences()) }

    /// `sensoryFeedback` that respects the Haptics preference.
    func suzentFeedback<Trigger: Equatable>(_ feedback: SensoryFeedback, trigger: Trigger) -> some View {
        modifier(OptionalFeedback(trigger: trigger) { _, _ in feedback })
    }

    func suzentFeedback<Trigger: Equatable>(trigger: Trigger, _ feedback: @escaping (Trigger, Trigger) -> SensoryFeedback?) -> some View {
        modifier(OptionalFeedback(trigger: trigger, feedback: feedback))
    }
}

struct PreferencesSection: View {
    @AppStorage(StoredPreference.appearance) private var appearance: AppearancePreference = .system
    @AppStorage(StoredPreference.textSize) private var textSize: TextSizePreference = .system
    @AppStorage(StoredPreference.haptics) private var haptics = true
    @Environment(\.openURL) private var openURL
    let header: AnyView

    var body: some View {
        Section {
            Picker("Appearance", selection: $appearance) {
                ForEach(AppearancePreference.allCases) { Text($0.title).tag($0) }
            }
            Picker("Text size", selection: $textSize) {
                ForEach(TextSizePreference.allCases) { Text($0.title).tag($0) }
            }
            Toggle("Haptics", isOn: $haptics).tint(Color(presentation: PresentationTokens.blue))
            Button {
                if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
            } label: {
                HStack {
                    Text("Language").foregroundStyle(Color.suzentText)
                    Spacer()
                    Text(Locale.current.localizedString(forLanguageCode: Bundle.main.preferredLocalizations.first ?? "en") ?? "")
                        .foregroundStyle(Color.suzentMuted)
                    Image(systemName: "arrow.up.forward").font(.caption).foregroundStyle(Color.suzentMuted)
                }
            }
        } header: { header } footer: {
            Text("These settings apply to this phone only. Language opens iOS Settings for Suzent.").foregroundStyle(Color.suzentMuted)
        }
    }
}
