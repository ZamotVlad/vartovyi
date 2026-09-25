from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class CheckStatus(StrEnum):
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"


class FailureReason(StrEnum):
    TIMEOUT = "timeout"
    DNS_ERROR = "dns_error"
    TLS_ERROR = "tls_error"
    CONNECTION_ERROR = "connection_error"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Сирий факт: що сталось на дроті. Без інтерпретації."""

    elapsed_ms: float
    status_code: int | None = None
    body_snippet: str | None = None
    failure: FailureReason | None = None


@dataclass(frozen=True, slots=True)
class Expectation:
    """Що користувач вважає нормою для цієї цілі."""

    expected_status: int = 200
    max_response_ms: float | None = None
    keyword: str | None = None


@dataclass(frozen=True, slots=True)
class CheckTarget:
    """Що і як перевіряти. Знімок монітора без прив'язки до ORM-сесії."""

    monitor_id: UUID
    url: str
    timeout_ms: int
    expectation: Expectation


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Вердикт: статус і людиночитана причина."""

    status: CheckStatus
    reason: str | None = None


def evaluate(probe: ProbeResult, expectation: Expectation) -> Evaluation:
    if probe.failure is not None:
        return Evaluation(CheckStatus.DOWN, f"Мережева помилка: {probe.failure}")

    if probe.status_code != expectation.expected_status:
        return Evaluation(
            CheckStatus.DOWN,
            f"Очікували {expectation.expected_status}, отримали {probe.status_code}",
        )

    if expectation.keyword is not None:
        body = probe.body_snippet or ""
        if expectation.keyword not in body:
            return Evaluation(
                CheckStatus.DOWN,
                f"У відповіді немає рядка {expectation.keyword!r}",
            )

    if expectation.max_response_ms is not None and probe.elapsed_ms > expectation.max_response_ms:
        return Evaluation(
            CheckStatus.DEGRADED,
            f"Відповідь за {probe.elapsed_ms:.0f} мс, поріг {expectation.max_response_ms:.0f} мс",
        )

    return Evaluation(CheckStatus.UP)


def is_available(status: CheckStatus) -> bool:
    """DEGRADED вважається доступністю: повільно, але працює."""
    return status in (CheckStatus.UP, CheckStatus.DEGRADED)
