import Foundation

/// Decides whether a touch is a horizontal swipe or a vertical scroll.
///
/// The lock is taken once, at the first sample that travels `minTravel` (24 pt/dp)
/// in either axis, and it never flips. Horizontal wins only when the gesture is
/// within 30° of the x axis: `|dx| >= |dy| * sqrt(3)`. A scroll that has already
/// started (`noteVerticalScroll`) keeps the gesture. Vertical intent locks early at 8 pt/dp.
public struct SwipeAxisLock: Sendable, Equatable {
    public enum Axis: String, Sendable, Equatable {
        case undecided, horizontal, vertical
    }

    /// Minimum travel, in the caller's pixels, before either axis may lock.
    public static let minTravel: Double = 24
    /// `|dx| / |dy|` for a 30° cone around the horizontal axis.
    public static let dominance: Double = 3.squareRoot()
    /// Release past this distance commits a swipe action.
    public static let trigger: Double = 96
    public static let scrollTravel: Double = 8
    public static let flickTravel: Double = 56
    /// A flick at least this fast (px/s) commits after `flickTravel`, in the offset's direction.
    public static let velocityTrigger: Double = 900

    public private(set) var axis: Axis = .undecided

    public init() {}

    /// The parent scroller has taken the touch. Later horizontal movement must not steal it.
    public mutating func noteVerticalScroll() {
        if axis == .undecided { axis = .vertical }
    }

    public mutating func update(dx: Double, dy: Double) -> Axis {
        if axis != .undecided { return axis }
        let adx = abs(dx)
        let ady = abs(dy)
        if ady >= Self.scrollTravel && adx < ady * Self.dominance {
            axis = .vertical
            return axis
        }
        if adx < Self.minTravel && ady < Self.minTravel { return .undecided }
        // The epsilon keeps an exact 30° sample on the horizontal side of the comparison.
        axis = adx >= Self.minTravel && adx + 1e-9 >= ady * Self.dominance ? .horizontal : .vertical
        return axis
    }

    public mutating func reset() { axis = .undecided }

    /// Commit a swipe that has already locked horizontal. `offset` is signed; `velocity` is px/s
    /// along the same axis (positive means toward the trailing edge).
    public static func commits(offset: Double, velocity: Double) -> Bool {
        let travel = abs(offset)
        if travel < minTravel { return false }
        let along = offset < 0 ? -velocity : velocity
        if along <= -velocityTrigger { return false }
        return travel >= trigger || (travel >= flickTravel && along >= velocityTrigger)
    }

    /// Angle check for a platform recognizer that must accept or reject at its own, smaller
    /// touch slop (the system back-swipe asks before `minTravel`). Vertical still wins ties.
    /// In-app swipes use `update`, which also requires `minTravel`.
    public static func angleIsHorizontal(dx: Double, dy: Double, vx: Double = 0, vy: Double = 0) -> Bool {
        let adx = abs(dx)
        let ady = abs(dy)
        if adx >= 1 || ady >= 1 {
            if ady > adx { return false }
            return adx + 1e-9 >= ady * dominance
        }
        let avx = abs(vx)
        let avy = abs(vy)
        if avx < 1 && avy < 1 { return false }
        return avx > avy && avx + 1e-9 >= avy * dominance
    }
}
