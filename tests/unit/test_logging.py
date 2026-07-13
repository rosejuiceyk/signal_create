from __future__ import annotations

import json
import logging

from he3sim.logging import JsonFormatter


def test_json_formatter_emits_parseable_structured_context() -> None:
    record = logging.LogRecord(
        name="he3sim.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="configuration validated",
        args=(),
        exc_info=None,
    )
    record.context = {"seed": 7, "parameter_status": "synthetic_demo"}

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["message"] == "configuration validated"
    assert payload["context"] == {"seed": 7, "parameter_status": "synthetic_demo"}
