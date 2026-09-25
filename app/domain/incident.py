from collections.abc import Sequence
from enum import StrEnum

from app.domain.check import CheckStatus, is_available


class IncidentAction(StrEnum):
    OPEN = "open"
    RESOLVE = "resolve"
    NONE = "none"


def decide_incident_action(
    recent: Sequence[CheckStatus], *, has_open_incident: bool, failure_threshold: int
) -> IncidentAction:
    """Що робити з інцидентом після нової перевірки.

    recent - останні статуси в хронологічному порядку, найновіший останній.
    Інцидент відкривається лише після failure_threshold падінь поспіль,
    щоб одиничний мережевий збій не будив людей серед ночі. Закривається
    першою ж успішною перевіркою.
    """
    if not recent:
        return IncidentAction.NONE

    if has_open_incident:
        return IncidentAction.RESOLVE if is_available(recent[-1]) else IncidentAction.NONE

    window = recent[-failure_threshold:]
    if len(window) == failure_threshold and not any(is_available(s) for s in window):
        return IncidentAction.OPEN
    return IncidentAction.NONE
