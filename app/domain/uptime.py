from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.check import CheckStatus, is_available


@dataclass(frozen=True, slots=True)
class UptimeSummary:
    total: int
    up: int
    degraded: int
    down: int

    @property
    def ratio(self) -> float | None:
        """Частка доступності від 0 до 1. None, якщо даних немає."""
        if self.total == 0:
            return None
        return (self.up + self.degraded) / self.total

    @property
    def percent(self) -> float | None:
        ratio = self.ratio
        return None if ratio is None else round(ratio * 100, 3)


def summarize(statuses: Sequence[CheckStatus]) -> UptimeSummary:
    counts = Counter(statuses)
    return UptimeSummary(
        total=len(statuses),
        up=counts[CheckStatus.UP],
        degraded=counts[CheckStatus.DEGRADED],
        down=counts[CheckStatus.DOWN],
    )


def longest_down_streak(statuses: Sequence[CheckStatus]) -> int:
    """Найдовша серія падінь підряд. Основа для створення інциденту."""
    longest = 0
    current = 0
    for status in statuses:
        if is_available(status):
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest
