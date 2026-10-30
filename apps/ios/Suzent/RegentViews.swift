import SwiftUI
import SuzentCore

struct RegentMark: View {
    var working = false
    var waiting = false
    var size: CGFloat = 32
    var lastMessageAt: String?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var nod = false

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion || scenePhase != .active || (!working && !waiting))) { context in
            let t = reduceMotion ? 0 : context.date.timeIntervalSinceReferenceDate
            let lift = working && !reduceMotion ? 1 + sin(t * 2) : 0
            let scan = working && !reduceMotion ? sin(t * 2) * 1.2 : 0
            Canvas { context, canvas in
                context.scaleBy(x: canvas.width / 24, y: canvas.height / 36)
                let ink = Color.suzentText
                let eyes = Color.suzentBackground
                context.fill(Path(roundedRect: CGRect(x: 0, y: 12, width: 24, height: 24), cornerRadius: 4), with: .color(ink))
                for x in [5.0, 14.0] {
                    context.fill(Path(roundedRect: CGRect(x: x + scan, y: 20, width: 5, height: 5), cornerRadius: 1.5), with: .color(eyes))
                }
                var crown = Path()
                crown.move(to: CGPoint(x: 3, y: 5 - lift))
                crown.addQuadCurve(to: CGPoint(x: 21, y: 5 - lift), control: CGPoint(x: 12, y: 1.4 - lift))
                crown.addLine(to: CGPoint(x: 21, y: 8 - lift))
                crown.addQuadCurve(to: CGPoint(x: 3, y: 8 - lift), control: CGPoint(x: 12, y: 11.6 - lift))
                crown.closeSubpath()
                context.fill(crown, with: .color(ink))
                var gem = Path()
                gem.move(to: CGPoint(x: 12, y: 5 - lift))
                gem.addLine(to: CGPoint(x: 14.4, y: 7.4 - lift))
                gem.addLine(to: CGPoint(x: 12, y: 9.8 - lift))
                gem.addLine(to: CGPoint(x: 9.6, y: 7.4 - lift))
                gem.closeSubpath()
                let pulse = waiting && !working && !reduceMotion ? 0.75 + 0.25 * sin(t * 3) : 1
                context.fill(gem, with: .color((waiting && !working ? Color.orange : eyes).opacity(pulse)))
            }
            .rotation3DEffect(.degrees(working && !reduceMotion ? sin(t * 1.4) * 12 : 0), axis: (x: 0, y: 1, z: 0))
        }
        .frame(width: size, height: size * 1.5)
        .rotationEffect(.degrees(nod ? -7 : 0))
        .onChange(of: lastMessageAt) { old, new in
            guard old != nil, new != nil, !reduceMotion else { return }
            withAnimation(.easeInOut(duration: 0.18).repeatCount(2, autoreverses: true)) { nod = true }
        }
        .task(id: lastMessageAt) {
            try? await Task.sleep(for: .milliseconds(750))
            nod = false
        }
        .accessibilityHidden(true)
    }
}

struct RegentIdentity: View {
    var working = false
    var waiting = 0
    var unread = 0
    var lastMessageAt: String?
    var expanded = false
    var showStatus = true

    var body: some View {
        HStack(spacing: 12) {
            RegentMark(working: working, waiting: waiting > 0, size: expanded ? 44 : 24, lastMessageAt: lastMessageAt)
            VStack(alignment: .leading, spacing: 4) {
                Text("SUZENT Regent").suzentFont(14, weight: .semibold)
                if showStatus {
                    Text(working ? String(localized: "Regent is working") : waiting > 0 ? String(localized: "Needs your attention") : String(localized: "Across all your projects"))
                        .suzentFont(PresentationTokens.typeLabel).foregroundStyle(waiting > 0 && !working ? Color.orange : Color.suzentMuted)
                }
            }
            if unread > 0 { Text("\(unread)").font(.caption.bold()).padding(6).background(Color.suzentSelection).accessibilityLabel(Text("\(unread) unread messages")) }
        }.foregroundStyle(Color.suzentText)
    }
}

struct RegentGreeting: View {
    var body: some View {
        VStack(spacing: 16) {
            RegentMark(size: 64)
            Text("SUZENT Regent").font(.title2.bold())
            Text("One conversation for all your projects. Ask what needs you, or hand me your next task.")
                .foregroundStyle(Color.suzentMuted).multilineTextAlignment(.center)
        }.frame(maxWidth: .infinity).padding(.vertical, 36)
    }
}
