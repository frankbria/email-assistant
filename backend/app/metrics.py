"""The metrics command (spec AC-3.3, AC-3.4, AC-4.1-AC-4.3): `uv run python -m app.metrics [test-set.jsonl]`.

The pipeline decides every line of the calibration test set (§10.7) again, after calibration corrections: each of
the owner's other reactions is an example, as the reaction made it. A line never sees its own reaction, which would
give its answer away. It all happens in a scratch database, dropped afterwards, so the owner's data is left alone.
Prints each metric with PASS or FAIL against its threshold; the exit code is 1 when any fails.

The test set records the owner's verb, not their edits, so "accepted unchanged or with only a draft edit" (AC-3.3)
is a proposal whose verb is the owner's."""

import asyncio
import json
import re
import sys
import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Any, NamedTuple

from beanie import PydanticObjectId

from app.config import get_settings
from app.main import init_db
from app.models.example import Example
from app.models.job import Job
from app.models.message import Message
from app.pipeline.examples import record_example
from app.pipeline.run import decide_on
from app.services.ai_provider import AIProvider, provider_for

OWNER = "metrics"
NOISE = {"archive_noise", "digest"}  # mail that doesn't need the owner is archived or pulled into a digest (§10.5)
MOST_FOR_ONE_VERB = 0.5
ACCEPTED = 0.7
NEEDS_ME_AS_NOISE = 0.02
NOISE_FOUND = 0.8
# shortcut: word lists spot-check AC-3.4 as the spec allows; widen them when the test set shows misses.
TIME_LANGUAGE = re.compile(  # no "may", "sat", "sun", "wed" or "mar": they're everyday words too
    r"\b(meet\w*|call|schedul\w*|calendar|appointment|availab\w*|invite|zoom|today|tonight|tomorrow|noon|morning|"
    r"afternoon|evening|week|weekend|(mon|tues|wednes|thurs|fri|satur|sun)day|mon|tues?|thu(rs?)?|fri|january|"
    r"february|march|april|june?|july?|august|september|october|november|december|jan|feb|apr|aug|sept?|oct|nov|dec|"
    r"\d{1,2}(:\d{2})?\s*[ap]\.?m\.?|\d{1,2}:\d{2}|o'clock)\b",
    re.IGNORECASE,
)
SCHEDULING = re.compile(  # meeting words, or a clock time the job made up
    r"\b(meet(ing)?s?|call|schedul\w*|reschedul\w*|calendar|appointment|availab\w*|time slots?|"
    r"\d{1,2}(:\d{2})?\s*[ap]\.?m\.?|\d{1,2}:\d{2})\b",
    re.IGNORECASE,
)

Line = dict[str, Any]


class Metric(NamedTuple):
    name: str
    passed: bool
    detail: str


def message_of(line: Line, message_id: PydanticObjectId) -> Message:
    """The line's mail as the pipeline sees it; never stored."""
    return Message.model_validate(
        {
            "_id": message_id,
            "owner_id": OWNER,
            "plugin_id": "test-set",
            "ref": line["message_id"],
            "message_id": line["message_id"],
            "sender": {"email": line["sender"]},
            "to": [],
            "cc": [],
            "date": datetime.fromisoformat(line["reacted_at"]),
            "subject": line["subject"],
            "snippet": line["text"][:200],
            "list_id": line["list_id"],
        }
    )


async def evaluate(lines: Sequence[Line], provider: AIProvider) -> list[Job]:
    """The pipeline's decision on each line after calibration corrections, in order. One AI call per line."""
    # One id per email: holding a line out holds out every reaction to it (a re-run calibration repeats emails).
    # A missing Message-ID ("" from IMAP) says nothing about sameness, so each such line is its own email.
    keys = [line["message_id"].strip() or f"line {number}" for number, line in enumerate(lines)]
    ids = {key: PydanticObjectId() for key in keys}
    messages = [message_of(line, ids[key]) for line, key in zip(lines, keys, strict=True)]
    for message, line in zip(messages, lines, strict=True):
        await record_example(message, line["text"], line["owner_verb"], "calibration")
    jobs = []
    for message, line in zip(messages, lines, strict=True):
        await Example.find(Example.owner_id == OWNER, Example.message_id == message.id).delete()
        jobs.append(await decide_on(message, line["text"], provider, cap=None))
        await record_example(message, line["text"], line["owner_verb"], "calibration")
    return jobs


def rate(name: str, count: int, total: int, threshold: float, at_most: bool) -> Metric:
    if total == 0:
        return Metric(name, False, "no messages to measure")
    share = count / total
    passed = share <= threshold if at_most else share >= threshold
    return Metric(name, passed, f"{count}/{total} = {share:.0%} ({'max' if at_most else 'min'} {threshold:.0%})")


def measure(lines: Sequence[Line], jobs: Sequence[Job]) -> list[Metric]:
    """`jobs[i]` is the decision on `lines[i]`. An ask-owner card proposes nothing, so it classifies nothing."""
    pairs = list(zip(lines, jobs, strict=True))
    proposals = [(line, job) for line, job in pairs if proposes(job)]
    verbs = Counter(job.verb for _, job in proposals)
    top, most = verbs.most_common(1)[0] if verbs else ("none", 0)
    accepted = sum(job.verb == line["owner_verb"] for line, job in proposals)
    timeless = [(line, job) for line, job in pairs if not TIME_LANGUAGE.search(f"{line['subject']} {line['text']}")]
    scheduling = [line["subject"] for line, job in timeless if proposes(job) and SCHEDULING.search(job_text(job))]
    as_noise = [not job.ask_owner and job.verb in NOISE for _, job in pairs]
    needs_me = [noise for (line, _), noise in zip(pairs, as_noise, strict=True) if line["owner_verb"] not in NOISE]
    owner_noise = [noise for (line, _), noise in zip(pairs, as_noise, strict=True) if line["owner_verb"] in NOISE]
    return [
        rate(f"AC-3.3 verb spread: largest non-noise verb {top}", most, len(proposals), MOST_FOR_ONE_VERB, at_most=True),
        rate("AC-3.3 acceptance: non-noise proposals with the owner's verb", accepted, len(proposals), ACCEPTED, at_most=False),
        Metric(
            "AC-3.4 scheduling jobs for mail without meeting or time language",
            not scheduling,
            f"{len(scheduling)} of {len(timeless)}" + (f": {', '.join(scheduling)}" if scheduling else ""),
        ),
        rate("AC-4.1 owner-marked needs-me classified as noise", sum(needs_me), len(needs_me), NEEDS_ME_AS_NOISE, at_most=True),
        rate("AC-4.2 owner-marked noise classified as noise", sum(owner_noise), len(owner_noise), NOISE_FOUND, at_most=False),
    ]


def proposes(job: Job) -> bool:
    """A non-noise proposal: noise schedules nothing, whatever its title says."""
    return not job.ask_owner and job.verb not in NOISE


def job_text(job: Job) -> str:
    return " ".join([job.title, job.artifacts.draft or "", *job.artifacts.options])


async def run(path: str, provider: AIProvider) -> int:
    """Prints every metric; 1 when any fails, else 0."""
    with open(path, encoding="utf-8") as test_set:
        lines = [json.loads(text) for text in test_set if text.strip()]
    settings = get_settings()
    run_id = uuid.uuid4().hex[:12]  # its own database: a concurrent run must not share or drop it
    # shortcut: a killed run leaves its <db>_metrics_<id> database behind; drop those by hand, or sweep them if it recurs
    scratch = settings.model_copy(
        update={"mongodb_db": f"{settings.mongodb_db}_metrics_{run_id}", "mongodb_test_db": f"{settings.mongodb_test_db}_metrics_{run_id}"}
    )
    database = scratch.current_mongodb_db
    client = await init_db(scratch)
    try:
        metrics = measure(lines, await evaluate(lines, provider))
    finally:
        await client.drop_database(database)
        await client.close()
    print(f"{len(lines)} messages in {path}")
    for metric in metrics:
        print(f"{'PASS' if metric.passed else 'FAIL'}  {metric.name}: {metric.detail}")
    return 0 if all(metric.passed for metric in metrics) else 1


if __name__ == "__main__":
    settings = get_settings()
    sys.exit(
        asyncio.run(
            run(sys.argv[1] if len(sys.argv) > 1 else settings.test_set_file, provider_for(settings.ai_provider, settings.ai_model))
        )
    )
