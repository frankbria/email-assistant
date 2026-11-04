# Live Anthropic API (#93): the metrics command over a three-line test set, one AI call per line.
# Opt in with `uv run pytest -m integration`.
import json
import os
from pathlib import Path

import pytest

from app.config import get_settings
from app.metrics import run
from app.services.ai_provider import provider_for
from tests.test_metrics import line

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]


async def test_the_command_reports_every_metric_with_the_real_ai(tmp_path: Path, capsys):
    test_set = tmp_path / "test_set.jsonl"
    lines = [
        line("20% off garden tools this week", "archive_noise", "This week only: 20% off garden tools. Shop now."),
        line("Garden tools: the spring sale", "archive_noise", "Spring sale: garden tools from $5. Shop now."),
        line("Quote for the fence", "reply", "Hi Frank, can you send me a quote for the fence? Ann", "ann@example.com"),
    ]
    test_set.write_text("".join(json.dumps(entry) + "\n" for entry in lines))

    code = await run(str(test_set), provider_for(get_settings().ai_provider, get_settings().ai_model))

    report = capsys.readouterr().out
    assert code in (0, 1)
    assert sum(text.startswith(("PASS  AC-", "FAIL  AC-")) for text in report.splitlines()) == 5, report
