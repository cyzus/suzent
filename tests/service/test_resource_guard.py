from suzent.service.resource_guard import ResourceGuard


def test_resource_guard_requires_sustained_overage() -> None:
    guard = ResourceGuard(max_rss_bytes=100, consecutive_limit=3)

    assert guard.observe(101) is False
    assert guard.observe(150) is False
    assert guard.observe(99) is False
    assert guard.observe(101) is False
    assert guard.observe(101) is False
    assert guard.observe(101) is True


def test_resource_guard_remains_tripped_after_limit() -> None:
    guard = ResourceGuard(max_rss_bytes=100, consecutive_limit=1)

    assert guard.observe(101) is True
    assert guard.observe(102) is True
