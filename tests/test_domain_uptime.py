from app.domain.check import CheckStatus
from app.domain.uptime import longest_down_streak, summarize


def test_empty_history_has_no_ratio() -> None:
    summary = summarize([])
    assert summary.total == 0
    assert summary.ratio is None
    assert summary.percent is None


def test_all_up_is_full_availability() -> None:
    summary = summarize([CheckStatus.UP] * 10)
    assert summary.percent == 100.0


def test_degraded_counts_as_available() -> None:
    summary = summarize([CheckStatus.UP, CheckStatus.DEGRADED])
    assert summary.percent == 100.0
    assert summary.degraded == 1


def test_mixed_history_ratio() -> None:
    statuses = [CheckStatus.UP] * 9 + [CheckStatus.DOWN]
    assert summarize(statuses).percent == 90.0


def test_longest_streak_counts_consecutive_failures_only() -> None:
    statuses = [
        CheckStatus.DOWN,
        CheckStatus.DOWN,
        CheckStatus.UP,
        CheckStatus.DOWN,
        CheckStatus.DOWN,
        CheckStatus.DOWN,
        CheckStatus.UP,
    ]
    assert longest_down_streak(statuses) == 3


def test_no_failures_means_zero_streak() -> None:
    assert longest_down_streak([CheckStatus.UP, CheckStatus.DEGRADED]) == 0
