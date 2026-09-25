import pytest

from app.domain.check import CheckStatus
from app.domain.incident import IncidentAction, decide_incident_action

UP, DEGRADED, DOWN = CheckStatus.UP, CheckStatus.DEGRADED, CheckStatus.DOWN


@pytest.mark.parametrize(
    ("recent", "has_open", "expected"),
    [
        ([], False, IncidentAction.NONE),
        ([DOWN], False, IncidentAction.NONE),  # одиничний збій ще не інцидент
        ([UP, DOWN], False, IncidentAction.NONE),
        ([DOWN, DOWN], False, IncidentAction.OPEN),
        ([DEGRADED, DOWN], False, IncidentAction.NONE),  # повільно, але доступно
        ([DOWN, DOWN], True, IncidentAction.NONE),  # уже відкритий
        ([DOWN, UP], True, IncidentAction.RESOLVE),
        ([DOWN, DEGRADED], True, IncidentAction.RESOLVE),
        ([UP, UP], False, IncidentAction.NONE),
    ],
)
def test_decide_with_threshold_two(
    recent: list[CheckStatus], has_open: bool, expected: IncidentAction
) -> None:
    action = decide_incident_action(recent, has_open_incident=has_open, failure_threshold=2)
    assert action is expected


def test_threshold_one_opens_immediately() -> None:
    action = decide_incident_action([DOWN], has_open_incident=False, failure_threshold=1)
    assert action is IncidentAction.OPEN
