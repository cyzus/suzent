import SwiftUI
import UIKit
import SuzentCore

struct SuzentSwipeAction {
    var title: LocalizedStringKey
    var systemImage: String
    var tint: Color
    var ink: Color = .white
    var action: () -> Void
}

/// Horizontal row actions that stay out of a vertical scroll.
///
/// The row does not move until [SwipeAxisLock] locks horizontal. A vertical lock,
/// or a scroll that has already begun, leaves the touch with the list.
struct DirectionalSwipe<Content: View>: View {
    var enabled: Bool
    var leading: SuzentSwipeAction?
    var trailing: SuzentSwipeAction?
    @ViewBuilder var content: () -> Content
    @Environment(\.layoutDirection) private var layoutDirection
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var offset: CGFloat = 0
    @State private var armed = false
    @State private var armedTick = 0

    var body: some View {
        let rtl = layoutDirection == .rightToLeft
        ZStack {
            if offset != 0 {
                let action = offset > 0 ? leading : trailing
                HStack(spacing: 0) {
                    if offset > 0 {
                        actionLabel(action).padding(.leading, 20)
                        Spacer(minLength: 0)
                    } else {
                        Spacer(minLength: 0)
                        actionLabel(action).padding(.trailing, 20)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(action?.tint ?? .clear)
            }
            content()
                .offset(x: rtl ? -offset : offset)
        }
        .clipped()
        .background(SwipeRecognizerHost(enabled: enabled && (leading != nil || trailing != nil), rtl: rtl) { logical, _ in
            let limit: CGFloat = 120
            let lower: CGFloat = trailing == nil ? 0 : -limit
            let upper: CGFloat = leading == nil ? 0 : limit
            let next = min(max(logical, lower), upper)
            if abs(next) >= SwipeAxisLock.trigger && !armed {
                armed = true
                armedTick += 1
            } else if abs(next) < SwipeAxisLock.trigger {
                armed = false
            }
            offset = next
        } onEnd: { logical, velocity in
            if SwipeAxisLock.commits(offset: logical, velocity: velocity) {
                if logical > 0 { leading?.action() } else { trailing?.action() }
            }
            armed = false
            if reduceMotion { offset = 0 }
            else { withAnimation(.spring(duration: 0.28, bounce: 0)) { offset = 0 } }
        })
        .suzentFeedback(.impact(weight: .light), trigger: armedTick)
    }

    @ViewBuilder private func actionLabel(_ action: SuzentSwipeAction?) -> some View {
        if let action {
            Label(action.title, systemImage: action.systemImage)
                .labelStyle(.iconOnly)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(action.ink)
        }
    }
}

extension View {
    /// Leading reveals on a start-to-end swipe. Trailing reveals on an end-to-start swipe.
    func directionalSwipe(enabled: Bool, leading: SuzentSwipeAction? = nil, trailing: SuzentSwipeAction? = nil) -> some View {
        DirectionalSwipe(enabled: enabled, leading: leading, trailing: trailing) { self }
    }
}

/// Tightens the system back-swipe so a vertical scroll that starts at the edge does not pop.
struct NavigationPopGuard: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> PopGuardController { PopGuardController() }
    func updateUIViewController(_ controller: PopGuardController, context: Context) {}
}

final class PopGuardController: UIViewController {
    private var proxy: PopGestureProxy?

    override func didMove(toParent parent: UIViewController?) {
        super.didMove(toParent: parent)
        DispatchQueue.main.async { [weak self] in self?.bind() }
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        bind()
    }

    private func bind() {
        var current: UIViewController? = self
        var navigation: UINavigationController?
        while let candidate = current {
            if let found = candidate as? UINavigationController { navigation = found; break }
            if let found = candidate.navigationController { navigation = found; break }
            current = candidate.parent
        }
        guard let navigation, let pop = navigation.interactivePopGestureRecognizer else { return }
        if pop.delegate is PopGestureProxy { return }
        let proxy = PopGestureProxy(original: pop.delegate, navigation: navigation)
        self.proxy = proxy
        pop.delegate = proxy
    }
}

/// Forwards the navigation controller's existing pop-gesture answers, then applies the shared angle lock.
final class PopGestureProxy: NSObject, UIGestureRecognizerDelegate {
    weak var original: UIGestureRecognizerDelegate?
    weak var navigation: UINavigationController?

    init(original: UIGestureRecognizerDelegate?, navigation: UINavigationController) {
        self.original = original
        self.navigation = navigation
    }

    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        let allowed = original?.gestureRecognizerShouldBegin?(gestureRecognizer) ?? ((navigation?.viewControllers.count ?? 0) > 1)
        guard allowed, let pan = gestureRecognizer as? UIPanGestureRecognizer else { return allowed }
        let translation = pan.translation(in: pan.view)
        let velocity = pan.velocity(in: pan.view)
        return SwipeAxisLock.angleIsHorizontal(dx: translation.x, dy: translation.y, vx: velocity.x, vy: velocity.y)
    }

    override func responds(to aSelector: Selector!) -> Bool {
        if super.responds(to: aSelector) { return true }
        return original?.responds(to: aSelector) ?? false
    }

    override func forwardingTarget(for aSelector: Selector!) -> Any? {
        if original?.responds(to: aSelector) == true { return original }
        return super.forwardingTarget(for: aSelector)
    }
}

private final class DirectionLockedPan: UIGestureRecognizer, UIGestureRecognizerDelegate {
    var rtl = false
    var onChange: ((CGFloat, CGFloat) -> Void)?
    var onEnd: ((CGFloat, CGFloat) -> Void)?
    private var origin = CGPoint.zero
    private var lastPoint = CGPoint.zero
    private var lastTime: TimeInterval = 0
    private var logical: CGFloat = 0
    private var velocity: CGFloat = 0
    private var lock = SwipeAxisLock()
    private weak var frozenScroll: UIScrollView?

    override init(target: Any?, action: Selector?) {
        super.init(target: target, action: action)
        delegate = self
        cancelsTouchesInView = true
        delaysTouchesBegan = false
        delaysTouchesEnded = false
    }

    required init?(coder: NSCoder) { return nil }

    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool {
        // Stay simultaneous until the horizontal lock, so the list can scroll.
        state == .possible
    }

    override func reset() {
        super.reset()
        lock.reset()
        logical = 0
        velocity = 0
        thaw()
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent) {
        super.touchesBegan(touches, with: event)
        guard touches.count == 1, let touch = touches.first, let view else { state = .failed; return }
        origin = touch.location(in: view)
        lastPoint = origin
        lastTime = touch.timestamp
        lock.reset()
        logical = 0
        velocity = 0
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent) {
        super.touchesMoved(touches, with: event)
        guard let touch = touches.first, let view, state == .possible || state == .began || state == .changed else { return }
        let point = touch.location(in: view)
        let dx = point.x - origin.x
        let dy = point.y - origin.y
        logical = rtl ? -dx : dx
        switch lock.update(dx: logical, dy: dy) {
        case .undecided:
            break
        case .vertical:
            state = .failed
        case .horizontal:
            if state == .possible {
                state = .began
                freezeScroll()
            } else {
                state = .changed
            }
            let dt = max(touch.timestamp - lastTime, 0.001)
            let step = rtl ? -(point.x - lastPoint.x) : point.x - lastPoint.x
            velocity = step / dt
            lastPoint = point
            lastTime = touch.timestamp
            onChange?(logical, velocity)
        }
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent) {
        super.touchesEnded(touches, with: event)
        finish(cancelled: false)
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent) {
        super.touchesCancelled(touches, with: event)
        finish(cancelled: true)
    }

    private func finish(cancelled: Bool) {
        if state == .began || state == .changed {
            // A cancellation springs the row closed without committing the action.
            onEnd?(cancelled ? 0 : logical, cancelled ? 0 : velocity)
            state = cancelled ? .cancelled : .ended
        } else if state == .possible {
            state = .failed
        }
        thaw()
    }

    private func freezeScroll() {
        var current = view
        while let candidate = current {
            if let scroll = candidate as? UIScrollView {
                frozenScroll = scroll
                scroll.isScrollEnabled = false
                return
            }
            current = candidate.superview
        }
    }

    private func thaw() {
        frozenScroll?.isScrollEnabled = true
        frozenScroll = nil
    }
}

private final class SwipeHostView: UIView {
    let pan = DirectionLockedPan()

    override init(frame: CGRect) {
        super.init(frame: frame)
        isUserInteractionEnabled = false
        backgroundColor = .clear
    }

    required init?(coder: NSCoder) { return nil }

    override func didMoveToSuperview() {
        super.didMoveToSuperview()
        attach()
    }

    func attach() {
        guard let superview, pan.view !== superview else { return }
        pan.view?.removeGestureRecognizer(pan)
        superview.addGestureRecognizer(pan)
    }

    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? { nil }
}

private struct SwipeRecognizerHost: UIViewRepresentable {
    var enabled: Bool
    var rtl: Bool
    var onChange: (CGFloat, CGFloat) -> Void
    var onEnd: (CGFloat, CGFloat) -> Void

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> SwipeHostView {
        let view = SwipeHostView()
        bind(view, context: context)
        return view
    }

    func updateUIView(_ uiView: SwipeHostView, context: Context) {
        uiView.attach()
        bind(uiView, context: context)
    }

    static func dismantleUIView(_ uiView: SwipeHostView, coordinator: Coordinator) {
        uiView.pan.view?.removeGestureRecognizer(uiView.pan)
    }

    private func bind(_ view: SwipeHostView, context: Context) {
        view.pan.rtl = rtl
        view.pan.isEnabled = enabled
        context.coordinator.onChange = onChange
        context.coordinator.onEnd = onEnd
        view.pan.onChange = { logical, velocity in context.coordinator.onChange?(logical, velocity) }
        view.pan.onEnd = { logical, velocity in context.coordinator.onEnd?(logical, velocity) }
    }

    final class Coordinator {
        var onChange: ((CGFloat, CGFloat) -> Void)?
        var onEnd: ((CGFloat, CGFloat) -> Void)?
    }
}
