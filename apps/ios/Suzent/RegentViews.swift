import SwiftUI
import SuzentCore

private let crownCurve = UnitCurve.bezier(startControlPoint: UnitPoint(x: 0.22, y: 1), endControlPoint: UnitPoint(x: 0.36, y: 1))
private let headStops = [0, 0.26, 0.58, 0.8, 1.0]
private let crownStops = [0, 0.28, 0.58, 0.8, 1.0]
private let crownDuration = 0.62
private let glintDelay = 0.22
private let glintDuration = 0.65

private func keyframe(_ progress: Double, _ stops: [Double], _ values: [Double]) -> Double {
    guard let next = stops.indices.dropFirst().first(where: { progress <= stops[$0] }) else { return values[values.count - 1] }
    let local = (progress - stops[next - 1]) / (stops[next] - stops[next - 1])
    return values[next - 1] + (values[next] - values[next - 1]) * crownCurve.value(at: local)
}

/// Desktop's sidebar coronation (regentMark*Crown in styles.css), in this mark's 24×36 units.
private struct CrownPose {
    var headY = 0.0, headScaleX = 1.0, headScaleY = 1.0, eyesY = 0.0, eyesScaleY = 1.0
    var crownOpacity = 1.0, crownY = 0.0, crownScaleX = 1.0, crownScaleY = 1.0, crownRotation = 0.0, glint = 0.0

    // This mark's circlet floats 1 unit higher above the head than desktop's, so it travels 1 unit further.
    static let rest = CrownPose(headY: -1, crownOpacity: 0, crownY: -5, crownScaleX: 0.72, crownScaleY: 0.72, crownRotation: -10)

    static func at(_ elapsed: Double, eyes: Bool) -> CrownPose {
        let p = min(max(elapsed / crownDuration, 0), 1)
        let g = min(max((elapsed - glintDelay) / glintDuration, 0), 1)
        return CrownPose(
            headY: keyframe(p, headStops, [-1, -2.4, 1.4, -0.2, 0.4]),
            headScaleX: keyframe(p, headStops, [1, 0.95, 0.89, 0.85, 0.86]),
            headScaleY: keyframe(p, headStops, [1, 1.03, 0.81, 0.87, 0.86]),
            eyesY: eyes ? keyframe(p, crownStops, [0, -2.2, 0.6, -0.5, 0]) : 0,
            eyesScaleY: eyes ? keyframe(p, crownStops, [1, 1.08, 0.22, 1.04, 1]) : 1,
            crownOpacity: keyframe(p, crownStops, [0, 1, 1, 1, 1]),
            crownY: keyframe(p, crownStops, [-6, 1.4, 7.1, 5, 5.7]),
            crownScaleX: keyframe(p, crownStops, [0.72, 0.92, 0.92, 0.88, 0.88]),
            crownScaleY: keyframe(p, crownStops, [0.72, 0.92, 0.85, 0.88, 0.88]),
            crownRotation: keyframe(p, crownStops, [-12, 5, -1.5, 0.6, 0]),
            glint: g < 0.45 ? UnitCurve.easeOut.value(at: g / 0.45) : 1 - UnitCurve.easeOut.value(at: (g - 0.45) / 0.55))
    }

    func toward(_ target: CrownPose, _ amount: Double) -> CrownPose {
        func mix(_ from: Double, _ to: Double) -> Double { from + (to - from) * amount }
        return CrownPose(headY: mix(headY, target.headY), headScaleX: mix(headScaleX, target.headScaleX), headScaleY: mix(headScaleY, target.headScaleY),
                         eyesY: mix(eyesY, target.eyesY), eyesScaleY: mix(eyesScaleY, target.eyesScaleY), crownOpacity: mix(crownOpacity, target.crownOpacity),
                         crownY: mix(crownY, target.crownY), crownScaleX: mix(crownScaleX, target.crownScaleX), crownScaleY: mix(crownScaleY, target.crownScaleY),
                         crownRotation: mix(crownRotation, target.crownRotation), glint: mix(glint, target.glint))
    }
}

/// `coronation` nil keeps the circlet on. Otherwise the mark rests as the plain Suzent head, like the desktop
/// sidebar row, and true plays desktop's hover coronation (a phone has no hover, so callers pass the press).
struct RegentMark: View {
    var working = false
    var waiting = false
    var size: CGFloat = 32
    var lastMessageAt: String?
    var coronation: Bool?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var nod = false
    @State private var crownedAt: Date?
    @State private var releasedAt: Date?
    @State private var releasedPose = CrownPose.rest
    @State private var crownMoving = false

    private func pose(at now: Date) -> CrownPose {
        guard coronation != nil else { return CrownPose() }
        if reduceMotion { return crownedAt == nil ? .rest : .at(crownDuration, eyes: false) }
        if let crownedAt { return .at(now.timeIntervalSince(crownedAt), eyes: !working) }
        guard let releasedAt else { return .rest }
        let back = UnitCurve.easeOut.value(at: min(now.timeIntervalSince(releasedAt) / 0.26, 1))
        return releasedPose.toward(.rest, back)
    }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion || scenePhase != .active || (!working && !waiting && !crownMoving))) { context in
            let t = reduceMotion ? 0 : context.date.timeIntervalSinceReferenceDate
            let pose = pose(at: context.date)
            let lift = working && !reduceMotion ? (1 + sin(t * 2)) * pose.crownOpacity : 0
            let scan = working && !reduceMotion ? sin(t * 2) * 1.2 : 0
            Canvas { context, canvas in
                context.scaleBy(x: canvas.width / 24, y: canvas.height / 36)
                let ink = Color.suzentText
                let eyes = Color.suzentBackground
                var head = context
                head.translateBy(x: 12, y: 36 + pose.headY)
                head.scaleBy(x: pose.headScaleX, y: pose.headScaleY)
                head.translateBy(x: -12, y: -36)
                head.fill(Path(roundedRect: CGRect(x: 0, y: 12, width: 24, height: 24), cornerRadius: 4), with: .color(ink))
                var eyeContext = head
                eyeContext.translateBy(x: 12, y: 22.5 + pose.eyesY)
                eyeContext.scaleBy(x: 1, y: pose.eyesScaleY)
                eyeContext.translateBy(x: -12, y: -22.5)
                for x in [5.0, 14.0] {
                    eyeContext.fill(Path(roundedRect: CGRect(x: x + scan, y: 20, width: 5, height: 5), cornerRadius: 1.5), with: .color(eyes))
                }
                guard pose.crownOpacity > 0 else { return }
                var crownContext = context
                crownContext.opacity = pose.crownOpacity
                crownContext.translateBy(x: 12, y: 9.8 + pose.crownY - lift)
                crownContext.scaleBy(x: pose.crownScaleX, y: pose.crownScaleY)
                crownContext.rotate(by: .degrees(pose.crownRotation))
                crownContext.translateBy(x: -12, y: -9.8)
                var crown = Path()
                crown.move(to: CGPoint(x: 3, y: 5))
                crown.addQuadCurve(to: CGPoint(x: 21, y: 5), control: CGPoint(x: 12, y: 1.4))
                crown.addLine(to: CGPoint(x: 21, y: 8))
                crown.addQuadCurve(to: CGPoint(x: 3, y: 8), control: CGPoint(x: 12, y: 11.6))
                crown.closeSubpath()
                crownContext.fill(crown, with: .color(ink))
                var gem = Path()
                gem.move(to: CGPoint(x: 12, y: 5))
                gem.addLine(to: CGPoint(x: 14.4, y: 7.4))
                gem.addLine(to: CGPoint(x: 12, y: 9.8))
                gem.addLine(to: CGPoint(x: 9.6, y: 7.4))
                gem.closeSubpath()
                let pulse = waiting && !working && !reduceMotion ? 0.75 + 0.25 * sin(t * 3) : 1
                crownContext.fill(gem, with: .color((waiting && !working ? Color.orange : eyes).opacity(pulse)))
                if !waiting && pose.glint > 0 {
                    crownContext.fill(gem, with: .color(Color(presentation: PresentationTokens.yellow).opacity(pose.glint)))
                }
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
        .task(id: coronation) {
            let now = Date()
            if coronation == true {
                crownedAt = now
                releasedAt = nil
            } else if let started = crownedAt {
                releasedPose = .at(now.timeIntervalSince(started), eyes: !working)
                crownedAt = nil
                releasedAt = now
            } else { return }
            crownMoving = true
            try? await Task.sleep(for: .seconds(glintDelay + glintDuration))
            crownMoving = false
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
    var coronation: Bool?

    var body: some View {
        HStack(spacing: 12) {
            RegentMark(working: working, waiting: waiting > 0, size: expanded ? 44 : 24, lastMessageAt: lastMessageAt, coronation: coronation)
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

/// Plain button that reports its press, so a label can play desktop's hover animation on touch.
struct PressReportingButtonStyle: ButtonStyle {
    @Binding var pressed: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label.onChange(of: configuration.isPressed) { _, isPressed in pressed = isPressed }
    }
}
