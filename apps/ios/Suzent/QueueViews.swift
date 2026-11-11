import SwiftUI
import SuzentCore

/// Messages waiting for the running turn to end; any of them can redirect now instead, or be dropped.
struct QueuedMessagesView: View {
    var model: MobileModel

    var body: some View {
        let items = model.queued
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("\(items.count) queued · sent when this turn ends").textCase(.uppercase)
                        .suzentFont(PresentationTokens.typeLabel, weight: .bold).foregroundStyle(Color.suzentMuted)
                    Spacer(minLength: 8)
                    if items.count > 1 {
                        Button("Cancel all") { model.clearQueued() }.buttonStyle(.plain)
                            .suzentFont(PresentationTokens.typeLabel).foregroundStyle(Color.suzentMuted).frame(minHeight: 32)
                    }
                }
                ForEach(items) { item in
                    HStack(spacing: 4) {
                        VStack(alignment: .leading, spacing: 2) {
                            if !item.text.isEmpty { Text(item.text).suzentFont(14).lineLimit(3) }
                            if !item.attachments.isEmpty {
                                Text(item.attachments.map(\.name).joined(separator: ", ")).suzentFont(11)
                                    .foregroundStyle(Color.suzentMuted).lineLimit(1)
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                        if model.redirectSupported && !item.text.isEmpty {
                            Button("Redirect now") { Task { await model.redirectQueued(item) } }.buttonStyle(.plain)
                                .suzentFont(PresentationTokens.typeLabel, weight: .bold).padding(.horizontal, 8).frame(minHeight: 44)
                                .disabled(model.busy)
                        }
                        Button { model.removeQueued(item) } label: {
                            Image(systemName: "xmark").font(.system(size: 13, weight: .semibold)).frame(width: 44, height: 44)
                        }.buttonStyle(.plain).accessibilityLabel("Cancel this message")
                    }
                    .padding(.leading, 10)
                    .overlay(Rectangle().stroke(Color.suzentRowDivider, lineWidth: PresentationTokens.borderWidth))
                }
            }
        }
    }
}
