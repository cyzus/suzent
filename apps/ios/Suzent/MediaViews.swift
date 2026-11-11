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

/// The images, videos, audio and files a turn's tools made or sent, shown inline like the desktop's result gallery.
struct MediaGallery: View {
    let items: [MediaItem]
    @Environment(\.mediaLoader) private var loader

    var body: some View {
        if let loader, !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(items) { item in
                    if item.kind == "file" { FileRow(item: item, loader: loader) }
                    else { MediaTile(item: item, loader: loader) }
                }
            }
        }
    }
}

/// A sent document or archive: fetched only when the user asks for it, then shared.
private struct FileRow: View {
    let item: MediaItem
    let loader: MediaLoader
    @State private var file: URL?
    @State private var loading = false
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "doc").foregroundStyle(Color.suzentMuted)
                Text(item.name).suzentFont(PresentationTokens.typeMeta).lineLimit(1).truncationMode(.middle)
                Spacer(minLength: 0)
                if let file {
                    ShareLink(item: file) { Image(systemName: "square.and.arrow.up") }
                        .accessibilityLabel(Text("Share \(item.name)"))
                } else {
                    Button {
                        Task {
                            loading = true
                            failed = false
                            file = await loader.load(item)
                            failed = file == nil
                            loading = false
                        }
                    } label: { Image(systemName: "arrow.down.circle") }
                        .disabled(loading)
                        .accessibilityLabel(Text("Download \(item.name)"))
                }
            }.padding(.horizontal, 12).frame(minHeight: 44)
            if loading {
                Text(String(localized: "Loading \(item.name)…")).suzentFont(PresentationTokens.typeMeta)
                    .foregroundStyle(Color.suzentMuted).padding([.horizontal, .bottom], 12)
            } else if failed {
                Text(String(localized: "\(item.name) can't be opened. It may have been moved or deleted on your computer."))
                    .suzentFont(PresentationTokens.typeMeta).foregroundStyle(Color.suzentMuted).padding([.horizontal, .bottom], 12)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(Rectangle().stroke(Color.suzentOutline, lineWidth: 1))
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
