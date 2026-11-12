# AC-4.3: the committed synthetic test set the scheduled metrics workflow runs the metrics command against.
# It must look like a calibration test set and give every metric a denominator that means something.
# Real MongoDB (the command's scratch database); a fake AI that proposes the owner's own verb.
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

import pytest

from app.metrics import NOISE, TIME_LANGUAGE, run
from app.models.job import Verb
from app.pipeline.proposal import Proposal
from tests.test_metrics import BySubject

pytestmark = pytest.mark.usefixtures("test_db")

SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic_test_set.jsonl"
FIELDS = {"message_id", "sender", "list_id", "subject", "text", "proposed", "owner_verb", "reacted_at"}
FICTIONAL = (".example", ".test", "example.com", "example.net", "example.org")


def lines() -> list[dict[str, object]]:
    return [json.loads(text) for text in SYNTHETIC.read_text(encoding="utf-8").splitlines() if text.strip()]


def test_every_line_has_the_calibration_line_format_and_fictional_mail():
    for entry in lines():
        assert set(entry) == FIELDS, entry["subject"]
        assert entry["owner_verb"] in get_args(Verb)
        assert str(entry["sender"]).split("@")[1].endswith(FICTIONAL), entry["sender"]
        datetime.fromisoformat(str(entry["reacted_at"]))
    subjects = [entry["subject"] for entry in lines()]
    assert len(set(subjects)) == len(subjects)  # the fake AI below tells lines apart by subject


def test_every_verb_and_metric_has_a_meaningful_denominator():
    verbs = [entry["owner_verb"] for entry in lines()]
    assert set(verbs) == set(get_args(Verb))
    needs_me = [verb for verb in verbs if verb not in NOISE]
    assert len(needs_me) >= 50  # AC-4.1's 2%: below 50 needs-me lines, a single miss would already fail it
    assert len(verbs) - len(needs_me) >= 20  # AC-4.2's 80%: room for four misses, not zero
    timed = [TIME_LANGUAGE.search(f"{entry['subject']} {entry['text']}") is not None for entry in lines()]
    assert sum(timed) >= 5 and timed.count(False) >= 40  # AC-3.4 checks only the mail without time language


def proposal(entry: dict[str, object]) -> Proposal:
    """The owner's verb, with every artifact any verb needs; evidence quoted from the mail."""
    return Proposal(
        needs_owner=False,
        verb=entry["owner_verb"],
        title=f"About {entry['subject']}",  # type: ignore[arg-type]
        evidence=[" ".join(str(entry["text"]).split()[:3])],
        draft="Thanks, noted.",
        due=datetime(2026, 12, 1, tzinfo=UTC),
        noise_rationale="Bulk mail",
        digest="A summary",
        confidence=0.9,
    )


async def test_the_metrics_command_reports_every_metric_over_it(capsys):
    ai = BySubject({str(entry["subject"]): proposal(entry) for entry in lines()})

    assert await run(str(SYNTHETIC), ai) == 0

    out = capsys.readouterr().out
    for ac in ("AC-3.3 verb spread", "AC-3.3 acceptance", "AC-3.4", "AC-4.1", "AC-4.2"):
        assert f"PASS  {ac}" in out
