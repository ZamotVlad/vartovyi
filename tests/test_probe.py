import asyncio
import socket
import ssl
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.domain.check import CheckTarget, Expectation, FailureReason, ProbeResult
from app.services import check_runner
from app.services.check_runner import run_probes
from app.services.probe import classify_failure, probe

URL = "https://site.example.com/health"


def target(url: str = URL, keyword: str | None = None, timeout_ms: int = 5_000) -> CheckTarget:
    return CheckTarget(
        monitor_id=uuid.uuid4(),
        url=url,
        timeout_ms=timeout_ms,
        expectation=Expectation(keyword=keyword),
    )


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=None) as http:
        yield http


@respx.mock
async def test_probe_records_status_and_time(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(503)

    result = await probe(client, target(), timeout_s=1, body_max_bytes=1024)

    assert result.status_code == 503
    assert result.failure is None
    assert result.elapsed_ms >= 0
    assert result.body_snippet is None  # без keyword тіло не читаємо


@respx.mock
async def test_probe_reads_body_only_up_to_limit(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(200, text="ok" + "x" * 10_000)

    result = await probe(client, target(keyword="ok"), timeout_s=1, body_max_bytes=1024)

    assert result.body_snippet is not None
    assert result.body_snippet.startswith("ok")
    assert len(result.body_snippet) == 1024


@respx.mock
async def test_probe_timeout_covers_slow_response(client: httpx.AsyncClient) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)

    respx.get(URL).mock(side_effect=slow)

    result = await probe(client, target(), timeout_s=0.05, body_max_bytes=1024)

    assert result.failure is FailureReason.TIMEOUT
    assert result.elapsed_ms < 1_000


@respx.mock
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ConnectTimeout("t"), FailureReason.TIMEOUT),
        (httpx.ConnectError("refused"), FailureReason.CONNECTION_ERROR),
    ],
)
async def test_probe_maps_transport_errors(
    client: httpx.AsyncClient, error: Exception, expected: FailureReason
) -> None:
    respx.get(URL).mock(side_effect=error)

    result = await probe(client, target(), timeout_s=1, body_max_bytes=1024)

    assert result.failure is expected
    assert result.status_code is None


def chained(cause: BaseException) -> httpx.ConnectError:
    error = httpx.ConnectError("wrapped")
    error.__cause__ = cause
    return error


def test_classify_dns_error_from_cause_chain() -> None:
    assert classify_failure(chained(socket.gaierror(-2, "Name unknown"))) is FailureReason.DNS_ERROR


def test_classify_tls_error_from_cause_chain() -> None:
    assert classify_failure(chained(ssl.SSLCertVerificationError())) is FailureReason.TLS_ERROR


@respx.mock
async def test_run_probes_respects_concurrency_limit(client: httpx.AsyncClient) -> None:
    in_flight = 0
    peak = 0

    async def tracked(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200)

    respx.get(url__startswith="https://").mock(side_effect=tracked)
    targets = [target(f"https://s{i}.example.com") for i in range(20)]

    results = await run_probes(client, targets, concurrency=3, max_timeout_s=1, body_max_bytes=1024)

    assert len(results) == 20
    assert peak == 3


@respx.mock
async def test_run_probes_isolates_each_timeout(client: httpx.AsyncClient) -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)

    respx.get("https://slow.example.com").mock(side_effect=hang)
    respx.get("https://fast.example.com").respond(200)
    targets = [
        target("https://slow.example.com", timeout_ms=100),
        target("https://fast.example.com", timeout_ms=100),
    ]

    results = await run_probes(client, targets, concurrency=5, max_timeout_s=1, body_max_bytes=1)

    by_url = {t.url: r for t, r in results}
    assert by_url["https://slow.example.com"].failure is FailureReason.TIMEOUT
    assert by_url["https://fast.example.com"].status_code == 200


@respx.mock
async def test_run_probes_caps_timeout_globally(client: httpx.AsyncClient) -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)

    respx.get(URL).mock(side_effect=hang)

    results = await run_probes(
        client, [target(timeout_ms=60_000)], concurrency=1, max_timeout_s=0.05, body_max_bytes=1
    )

    assert results[0][1].failure is FailureReason.TIMEOUT


async def test_crash_in_one_probe_does_not_cancel_others(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:

    async def flaky(
        client: httpx.AsyncClient, target: CheckTarget, **kwargs: object
    ) -> ProbeResult:
        if "boom" in target.url:
            raise ValueError("bug")
        return ProbeResult(elapsed_ms=1, status_code=200)

    monkeypatch.setattr(check_runner, "probe", flaky)
    targets = [target("https://boom.example.com"), target("https://ok.example.com")]

    results = await run_probes(client, targets, concurrency=2, max_timeout_s=1, body_max_bytes=1)

    assert [t.url for t, _ in results] == ["https://ok.example.com"]
