import AVKit
import ImageIO
import SwiftUI
import SuzentCore

/// Fetches a tool's media for the conversation on screen.
struct MediaLoader {
    let load: @MainActor (MediaItem) async -> URL?
}

private struct MediaLoaderKey: EnvironmentKey {
    nonisolated(unsafe) static let defaultValue: MediaLoader? = nil
}

extension EnvironmentValues {
    var mediaLoader: MediaLoader? {
        get { self[MediaLoaderKey.self] }
        set { self[MediaLoaderKey.self] = newValue }
    }
}

/// The images, videos and audio a turn's tools made, shown inline like the desktop's result gallery.
struct MediaGallery: View {
    let items: [MediaItem]
    @Environment(\.mediaLoader) private var loader

    var body: some View {
        if let loader, !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(items) { MediaTile(item: $0, loader: loader) }
            }
        }
    }
}

private struct MediaTile: View {
    let item: MediaItem
    let loader: MediaLoader
    @State private var image: UIImage?
    @State private var player: AVPlayer?
    @State private var failed = false

    var body: some View {
        content
            .frame(maxWidth: .infinity)
            .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 1))
            .task(id: item.id) { await load() }
            .onDisappear { player?.pause() }
    }

    @ViewBuilder private var content: some View {
        if failed {
            note(String(localized: "\(item.name) can't be opened. It may have been moved or deleted on your computer."))
        } else if let image {
            Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 360)
                .accessibilityLabel(Text(item.name))
        } else if let player {
            VideoPlayer(player: player).frame(height: item.kind == "audio" ? 80 : 240)
                .accessibilityLabel(Text(item.name))
        } else {
            note(String(localized: "Loading \(item.name)…"))
        }
    }

    private func note(_ text: String) -> some View {
        Text(text).suzentFont(PresentationTokens.typeMeta).foregroundStyle(Color.suzentMuted)
            .lineLimit(2).padding(12).frame(maxWidth: .infinity, alignment: .leading)
    }

    private func load() async {
        guard let file = await loader.load(item) else { failed = true; return }
        if item.kind == "image" {
            let decoded = await Task.detached(priority: .userInitiated) { downsampledImage(file) }.value
            if let decoded { image = decoded } else { failed = true }
        } else {
            player = AVPlayer(url: file)
        }
    }
}

/// Decodes at most about 1600 px on the long side, so a large render can't exhaust memory.
private func downsampledImage(_ url: URL) -> UIImage? {
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
    let options: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: 1600,
    ]
    guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return nil }
    return UIImage(cgImage: image)
}
