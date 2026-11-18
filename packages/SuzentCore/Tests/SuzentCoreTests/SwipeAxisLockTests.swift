import Testing
@testable import SuzentCore

@Test func horizontalLockNeedsThirtyDegreesAndMinimumTravel() {
    var undecided = SwipeAxisLock()
    #expect(undecided.update(dx: 23.9, dy: 0) == .undecided)
    #expect(undecided.axis == .undecided)

    var straight = SwipeAxisLock()
    #expect(straight.update(dx: 24, dy: 0) == .horizontal)

    var opposite = SwipeAxisLock()
    #expect(opposite.update(dx: -36, dy: 8) == .horizontal)

    let boundary = SwipeAxisLock.minTravel / SwipeAxisLock.dominance
    var onCone = SwipeAxisLock()
    #expect(onCone.update(dx: SwipeAxisLock.minTravel, dy: boundary) == .horizontal)
    var outsideCone = SwipeAxisLock()
    #expect(outsideCone.update(dx: SwipeAxisLock.minTravel, dy: boundary + 0.05) == .vertical)

    var equal = SwipeAxisLock()
    #expect(equal.update(dx: 40, dy: 40) == .vertical)
    var vertical = SwipeAxisLock()
    #expect(vertical.update(dx: 10, dy: 30) == .vertical)
}

@Test func directionLockSticksAndScrollWins() {
    var lock = SwipeAxisLock()
    #expect(lock.update(dx: 10, dy: 4) == .undecided)
    #expect(lock.update(dx: 12, dy: 30) == .vertical)
    #expect(lock.update(dx: 200, dy: 30) == .vertical)

    var scrolling = SwipeAxisLock()
    scrolling.noteVerticalScroll()
    #expect(scrolling.update(dx: 80, dy: 0) == .vertical)

    scrolling.reset()
    #expect(scrolling.axis == .undecided)
    #expect(scrolling.update(dx: 40, dy: 0) == .horizontal)
}

@Test func commitNeedsTriggerOrAFlickInTheSameDirection() {
    #expect(SwipeAxisLock.commits(offset: 96, velocity: 0))
    #expect(!SwipeAxisLock.commits(offset: 95, velocity: 0))
    #expect(!SwipeAxisLock.commits(offset: 30, velocity: 900))
    #expect(SwipeAxisLock.commits(offset: 56, velocity: 900))
    #expect(!SwipeAxisLock.commits(offset: -30, velocity: -900))
    #expect(SwipeAxisLock.commits(offset: -56, velocity: -900))
    #expect(!SwipeAxisLock.commits(offset: 30, velocity: -900))
    #expect(!SwipeAxisLock.commits(offset: 23, velocity: 2000))
    #expect(!SwipeAxisLock.commits(offset: 80, velocity: -900))
    #expect(SwipeAxisLock.commits(offset: -96, velocity: -100))
}

@Test func systemRecognizerUsesTheSameAngleBeforeMinimumTravel() {
    #expect(SwipeAxisLock.angleIsHorizontal(dx: 12, dy: 3))
    #expect(!SwipeAxisLock.angleIsHorizontal(dx: 12, dy: 10))
    #expect(!SwipeAxisLock.angleIsHorizontal(dx: 2, dy: 14))
    #expect(SwipeAxisLock.angleIsHorizontal(dx: 0, dy: 0, vx: 400, vy: 40))
    #expect(!SwipeAxisLock.angleIsHorizontal(dx: 0, dy: 0, vx: 40, vy: 400))
    #expect(!SwipeAxisLock.angleIsHorizontal(dx: 0, dy: 0, vx: 0, vy: 0))
}

@Test func earlyVerticalMovementCannotBecomeASwipe() {
    for direction in [-1.0, 1.0] {
        var lock = SwipeAxisLock()
        #expect(lock.update(dx: direction * 6, dy: 8) == .vertical)
        #expect(lock.update(dx: direction * 100, dy: 10) == .vertical)
        #expect(!SwipeAxisLock.commits(offset: direction * 40, velocity: direction * 2000))
    }
}
