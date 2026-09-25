import json
import logging
from collections.abc import Iterator

import pytest

from app.core.logging import configure_logging
from app.core.request_context import request_id_var


@pytest.fixture
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers, root.level = handlers, level
    logging.getLogger("uvicorn.access").disabled = False


@pytest.mark.usefixtures("restore_root_logger")
def test_json_logging_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")
    token = request_id_var.set("req-7")
    try:
        logging.getLogger("app.test").info("hello", extra={"monitor_id": "m1"})
    finally:
        request_id_var.reset(token)

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert line["message"] == "hello"
    assert line["request_id"] == "req-7"
    assert line["monitor_id"] == "m1"
    assert logging.getLogger("uvicorn.access").disabled


@pytest.mark.usefixtures("restore_root_logger")
def test_text_logging_includes_request_id(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", "text")
    logging.getLogger("app.test").info("hidden")
    logging.getLogger("app.test").warning("shown")

    out = capsys.readouterr().out

    assert "hidden" not in out
    assert "[None] app.test: shown" in out
