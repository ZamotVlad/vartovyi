from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class MonitorTiming:
    interval_seconds: int
    timeout_ms: int
    max_response_ms: int | None = None


def timing_violation(timing: MonitorTiming) -> str | None:
    """Пояснення, чому налаштування часу несумісні, або None, якщо все гаразд.

    Одне джерело правди для створення і часткового оновлення: при PATCH
    перевіряється вже об'єднаний стан, а не лише надіслані поля.
    """
    if timing.timeout_ms > timing.interval_seconds * 1000:
        return (
            "timeout_ms не може перевищувати interval_seconds: "
            "перевірки почнуть накладатись одна на одну"
        )
    if timing.max_response_ms is not None and timing.max_response_ms > timing.timeout_ms:
        return (
            "max_response_ms не може перевищувати timeout_ms: "
            "поріг деградації недосяжний, з'єднання обірветься раніше"
        )
    return None


class MonitorSort(StrEnum):
    """Дозволені порядки сортування списку. Префікс "-" означає спадання."""

    CREATED_DESC = "-created_at"
    CREATED_ASC = "created_at"
    NAME_ASC = "name"
    NAME_DESC = "-name"
