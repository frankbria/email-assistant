# The metrics command (spec AC-3.3, AC-3.4, AC-4.1-AC-4.3): the pipeline re-decides every test set line with the
# owner's other reactions as its examples, and one report scores the decisions against the owner's verbs.
# Real MongoDB (a scratch database); FakeAIProvider.
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from beanie import PydanticObjectId
from pydantic import BaseModel
from pymongo import AsyncMongoClient

from app.config import get_settings
from app.metrics import Metric, evaluate, measure, run
from app.models.job import Artifacts, Job, Verb
from app.pipeline.proposal import Proposal
from tests.utils.fakes import FakeAIProvider, SchemaT

pytestmark = pytest.mark.usefixtures("test_db")  # a Job is a Beanie document


def line(subject: str, owner_verb: Verb, text: str = "Thanks for the update on the garden tools order.",
         sender: str = "shop@example.com") -> dict[str, object]:
    return {"message_id": f"<{subject}@example.com>", "sender": sender, "list_id": None, "subject": subject,
            "text": text, "proposed": None, "owner_verb": owner_verb, "reacted_at": "2026-11-03T10:00:00+00:00"}


def job(verb: Verb, title: str = "The shop's order update", ask_owner: bool = False, draft: str | None = None) -> Job:
    return Job(owner_id="metrics", verb=verb, title=title, message_ids=[PydanticObjectId()], ask_owner=ask_owner,
               artifacts=Artifacts(draft=draft))


def outcome(metrics: list[Metric], ac: str) -> Metric:
    [found] = [metric for metric in metrics if metric.name.startswith(ac)]
    return found


class BySubject(FakeAIProvider):
    """The AI's proposal for each test set line, chosen by the subject in its prompt."""

    def __init__(self, proposals: dict[str, Proposal]) -> None:
        super().__init__()
        self.proposals = proposals

    async def propose(self, prompt: str, schema: type[SchemaT]) -> SchemaT:
        [subject] = [subject for subject in self.proposals if f"Subject: {subject}\n" in prompt]
        self.result: BaseModel | None = self.proposals[subject]
        return await super().propose(prompt, schema)


def noise(subject: str) -> Proposal:
    return Proposal(needs_owner=False, verb="archive_noise", title=f"The shop's {subject}", evidence=["garden tools"],
                    noise_rationale="A promotional mailing", confidence=0.9)


def reply(subject: str) -> Proposal:
    return Proposal(needs_owner=False, verb="reply", title=f"Ann asks about {subject}", evidence=["garden tools"],
                    draft="Thanks Ann, sounds good.", confidence=0.9)


def todo(subject: str) -> Proposal:
    return Proposal(needs_owner=False, verb="todo", title=f"Pay the shop's {subject}", evidence=["garden tools"],
                    due=datetime(2026, 11, 20, tzinfo=UTC), confidence=0.9)


def test_ac_3_3_no_verb_may_pass_half_of_the_non_noise_proposals():
    lines = [line(str(n), "reply") for n in range(4)] + [line("n", "archive_noise")]
    half = [job("reply"), job("reply"), job("todo"), job("forward"), job("archive_noise")]
    assert outcome(measure(lines, half), "AC-3.3 verb spread").passed  # noise and ask-owner cards don't count
    most = [job("reply"), job("reply"), job("reply"), job("todo"), job("archive_noise")]
    assert not outcome(measure(lines, most), "AC-3.3 verb spread").passed


def test_ac_3_3_seventy_percent_of_non_noise_proposals_are_the_owners_verb():
    lines = [line(str(n), "reply") for n in range(10)] + [line("asked", "reply")]
    seven = [job("reply")] * 7 + [job("todo")] * 3 + [job("reply", ask_owner=True)]
    assert outcome(measure(lines, seven), "AC-3.3 acceptance").passed
    six = [job("reply")] * 6 + [job("todo")] * 4 + [job("reply", ask_owner=True)]
    assert not outcome(measure(lines, six), "AC-3.3 acceptance").passed


def test_ac_3_4_no_scheduling_job_for_mail_without_meeting_or_time_language():
    lines = [line("Order shipped", "reply"), line("Lunch?", "reply", text="Can we meet on Tuesday at 1pm?")]
    scheduling = "Happy to schedule a meeting, when are you available?"
    assert outcome(measure(lines, [job("reply"), job("reply", draft=scheduling)]), "AC-3.4").passed
    failed = outcome(measure(lines, [job("reply", draft=scheduling), job("reply")]), "AC-3.4")
    assert not failed.passed and "Order shipped" in failed.detail
    made_up_time = outcome(measure(lines, [job("reply", draft="Does Tuesday 3pm suit you?"), job("reply")]), "AC-3.4")
    assert not made_up_time.passed
    noise_title = [job("archive_noise", title="The shop's meeting-room furniture sale"), job("reply")]
    assert outcome(measure(lines, noise_title), "AC-3.4").passed  # noise schedules nothing


def test_ac_4_1_at_most_two_percent_of_needs_me_mail_is_classified_as_noise():
    lines = [line(str(n), "reply") for n in range(50)]
    one = [job("archive_noise")] + [job("reply")] * 49
    assert outcome(measure(lines, one), "AC-4.1").passed
    two = [job("digest")] * 2 + [job("reply")] * 48  # a digest is noise handling too (spec §10.5)
    assert not outcome(measure(lines, two), "AC-4.1").passed


def test_ac_4_2_eighty_percent_of_owner_marked_noise_is_classified_as_noise():
    lines = [line(str(n), "archive_noise") for n in range(5)]
    four = [job("archive_noise")] * 4 + [job("archive_noise", ask_owner=True)]  # asking isn't classifying
    assert outcome(measure(lines, four), "AC-4.2").passed
    three = [job("archive_noise")] * 3 + [job("reply")] * 2
    assert not outcome(measure(lines, three), "AC-4.2").passed


def test_a_rate_over_no_messages_fails():
    """An empty denominator measures nothing, so it can't pass (e.g. a test set without owner-marked noise)."""
    assert not outcome(measure([line("a", "reply")], [job("reply")]), "AC-4.2").passed


async def test_each_line_is_decided_with_the_owners_other_reactions_as_examples():
    """AC-4.2 "after calibration corrections": every reaction is an example, but never for the line it came from."""
    lines = [line("Weekly deals #1", "archive_noise"), line("Weekly deals #2", "archive_noise")]
    ai = BySubject({"Weekly deals #1": noise("deals #1"), "Weekly deals #2": noise("deals #2")})

    jobs = await evaluate(lines, ai)

    assert [found.verb for found in jobs] == ["archive_noise", "archive_noise"]
    first, second = ai.prompts
    assert 'subject "Weekly deals #2"' in first and 'subject "Weekly deals #1"' not in first
    assert 'subject "Weekly deals #1"' in second and 'subject "Weekly deals #2"' not in second


async def test_one_command_reports_every_metric_and_fails_on_any_fail(tmp_path: Path, capsys):
    """AC-4.3: both noise metrics (and the rest) from one command, whose exit code is the verdict."""
    test_set = tmp_path / "test_set.jsonl"
    lines = [line("Deals", "archive_noise"), line("Question", "reply"), line("Invoice", "todo")]
    test_set.write_text("".join(json.dumps(entry) + "\n" for entry in lines))
    ai = BySubject({"Deals": noise("deals"), "Question": reply("the order"), "Invoice": todo("invoice")})

    assert await run(str(test_set), ai) == 0
    passing = capsys.readouterr().out
    for ac in ("AC-3.3 verb spread", "AC-3.3 acceptance", "AC-3.4", "AC-4.1", "AC-4.2"):
        assert f"PASS  {ac}" in passing

    ai.proposals["Deals"] = reply("the deals")
    assert await run(str(test_set), ai) == 1
    failing = capsys.readouterr().out
    assert "FAIL  AC-4.2" in failing and "FAIL  AC-3.3 verb spread" in failing
    databases = await AsyncMongoClient(get_settings().current_mongodb_uri).list_database_names()
    assert not [name for name in databases if "_metrics" in name]  # the scratch database is gone


async def test_a_line_never_sees_another_reaction_to_the_same_email():
    """Calibrating the same inbox twice records the email twice: either copy would give the other's answer away."""
    first, again = line("Weekly deals #1", "archive_noise"), line("Weekly deals #1", "archive_noise")
    other = line("Weekly deals #2", "archive_noise")
    ai = BySubject({"Weekly deals #1": noise("deals #1"), "Weekly deals #2": noise("deals #2")})

    await evaluate([first, again, other], ai)

    for prompt in ai.prompts[:2]:
        assert 'subject "Weekly deals #1"' not in prompt and 'subject "Weekly deals #2"' in prompt




async def test_a_run_leaves_another_runs_scratch_database_alone(tmp_path: Path):
    """Each command (its own process) gets its own scratch database, so one finishing never drops another's."""
    test_set = tmp_path / "test_set.jsonl"
    test_set.write_text(json.dumps(line("Deals", "archive_noise")) + "\n")
    other = AsyncMongoClient(get_settings().current_mongodb_uri)
    another_run = other[f"{get_settings().current_mongodb_db}_metrics"]  # the one name all runs once shared
    await another_run["examples"].insert_one({"owner_id": "metrics"})
    try:
        await run(str(test_set), BySubject({"Deals": noise("deals")}))

        assert await another_run["examples"].count_documents({}) == 1
    finally:
        await other.drop_database(another_run.name)
        await other.close()


async def test_emails_without_a_message_id_are_each_their_own_email():
    """The IMAP plugin reports a missing Message-ID as "": those emails must not be held out together."""
    first, second = line("Weekly deals #1", "archive_noise"), line("Weekly deals #2", "archive_noise")
    first["message_id"] = second["message_id"] = ""
    ai = BySubject({"Weekly deals #1": noise("deals #1"), "Weekly deals #2": noise("deals #2")})

    await evaluate([first, second], ai)

    assert 'subject "Weekly deals #2"' in ai.prompts[0] and 'subject "Weekly deals #1"' in ai.prompts[1]
