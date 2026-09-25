from app.domain.monitor import MonitorTiming, timing_violation


def test_consistent_timing_has_no_violation() -> None:
    assert timing_violation(MonitorTiming(60, 10_000, 2_000)) is None


def test_timeout_equal_to_interval_is_allowed() -> None:
    assert timing_violation(MonitorTiming(30, 30_000)) is None


def test_timeout_longer_than_interval() -> None:
    violation = timing_violation(MonitorTiming(30, 30_001))
    assert violation is not None
    assert "накладатись" in violation


def test_threshold_above_timeout() -> None:
    violation = timing_violation(MonitorTiming(60, 2_000, 2_001))
    assert violation is not None
    assert "недосяжний" in violation
