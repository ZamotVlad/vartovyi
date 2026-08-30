import pytest

from app.domain.check import (
    CheckStatus,
    Evaluation,
    Expectation,
    FailureReason,
    ProbeResult,
    evaluate,
    is_available,
)


def test_healthy_response_is_up() -> None:
    probe = ProbeResult(elapsed_ms=120.0, status_code=200)
    assert evaluate(probe, Expectation()) == Evaluation(CheckStatus.UP)


def test_network_failure_is_down() -> None:
    probe = ProbeResult(elapsed_ms=10000.0, failure=FailureReason.TIMEOUT)
    result = evaluate(probe, Expectation())
    assert result.status is CheckStatus.DOWN
    assert result.reason is not None


def test_unexpected_status_code_is_down() -> None:
    probe = ProbeResult(elapsed_ms=50.0, status_code=500)
    assert evaluate(probe, Expectation()).status is CheckStatus.DOWN


def test_custom_expected_status_is_respected() -> None:
    probe = ProbeResult(elapsed_ms=50.0, status_code=301)
    assert evaluate(probe, Expectation(expected_status=301)).status is CheckStatus.UP


def test_missing_keyword_is_down() -> None:
    probe = ProbeResult(elapsed_ms=50.0, status_code=200, body_snippet="Hello")
    expectation = Expectation(keyword="Vartovyi")
    assert evaluate(probe, expectation).status is CheckStatus.DOWN


def test_present_keyword_is_up() -> None:
    probe = ProbeResult(elapsed_ms=50.0, status_code=200, body_snippet="Vartovyi ok")
    expectation = Expectation(keyword="Vartovyi")
    assert evaluate(probe, expectation).status is CheckStatus.UP


def test_slow_but_correct_response_is_degraded() -> None:
    probe = ProbeResult(elapsed_ms=3000.0, status_code=200)
    expectation = Expectation(max_response_ms=2000.0)
    assert evaluate(probe, expectation).status is CheckStatus.DEGRADED


def test_slow_and_broken_response_is_down_not_degraded() -> None:
    """Порядок перевірок: код важливіший за швидкість."""
    probe = ProbeResult(elapsed_ms=3000.0, status_code=503)
    expectation = Expectation(max_response_ms=2000.0)
    assert evaluate(probe, expectation).status is CheckStatus.DOWN


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (CheckStatus.UP, True),
        (CheckStatus.DEGRADED, True),
        (CheckStatus.DOWN, False),
    ],
)
def test_availability_treats_degraded_as_available(status: CheckStatus, expected: bool) -> None:
    assert is_available(status) is expected
