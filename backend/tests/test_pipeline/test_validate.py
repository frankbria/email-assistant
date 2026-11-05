# Validate stage (spec §8.5, AC-3.1, AC-3.2): only grounded, specific, injection-safe proposals become
# jobs; anything else becomes an ask-owner job. Never a guess.
from datetime import UTC, datetime

import pytest

from app.models.job import Job
from app.models.message import Message
from app.pipeline.proposal import Proposal
from app.pipeline.validate import problems, to_job

BODY = (
    "Could we meet Thursday at 3pm to go over the Q4 budget?\nPay at https://vendor.example/pay/4471 by Friday.\n"
    "Details: https://trusted.example.evil.test/path."
)
HISTORY = ["Legal@Example.com"]


def proposal(**changes: object) -> Proposal:
    base = Proposal(
        needs_owner=False,
        verb="reply",
        title="Ana asks to meet Thursday about the Q4 budget",
        evidence=["Could we meet Thursday at 3pm"],
        options=["Thursday works", "Can't make it", "Later"],
        confidence=0.9,
    )
    return base.model_copy(update=changes)


def message() -> Message:
    return Message.model_validate(
        {
            "owner_id": "owner-1",
            "plugin_id": "proton",
            "ref": "r1",
            "message_id": "<m@x>",
            "sender": {"email": "ana@example.com"},
            "to": [],
            "cc": [],
            "date": datetime(2026, 11, 2, tzinfo=UTC),
            "subject": "Q4 budget review",
            "snippet": "Could we meet Thursday",
        }
    )


def test_a_grounded_specific_proposal_has_no_problems():
    assert problems(proposal(), BODY, HISTORY) == []


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"needs_owner": True}, "the AI wants the owner to decide"),
        ({"confidence": 0.3}, "the AI isn't confident"),
        ({"title": "Reply"}, "the title doesn't say what this email is"),
        ({"title": "  "}, "the title doesn't say what this email is"),
        ({"evidence": []}, "no evidence from the email"),
        ({"evidence": ["Could we meet Friday at 3pm"]}, "evidence not in the email: 'Could we meet Friday at 3pm'"),
        ({"options": [], "draft": None}, "a reply needs a draft or options"),
        ({"verb": "forward", "options": []}, "a forward needs a draft"),
        ({"verb": "digest", "options": []}, "a digest needs a summary or a reason"),
        ({"verb": "snooze", "options": []}, "a snooze needs a date"),
        ({"verb": "follow_up", "options": []}, "a follow-up needs a date"),
        ({"verb": "todo", "options": []}, "a todo needs a link or a deadline"),
        ({"verb": "archive_noise", "options": []}, "archiving as noise needs a reason"),
        ({"verb": "unsubscribe", "options": []}, "unsubscribing needs a reason"),
        ({"verb": "todo", "options": [], "link": "https://evil.example/login"}, "link not in the email: https://evil.example/login"),
        ({"verb": "forward", "draft": "FYI", "forward_to": "x@evil.example"}, "forward recipient not from history: x@evil.example"),
    ],
)
def test_each_failed_check_is_named(changes: dict[str, object], problem: str):
    assert problem in problems(proposal(**changes), BODY, HISTORY)


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"evidence": [""]}, "blank evidence"),
        ({"evidence": ["  \n "]}, "blank evidence"),
        ({"options": ["", "  "], "draft": " "}, "a reply needs a draft or options"),
        ({"verb": "archive_noise", "options": [], "noise_rationale": "  "}, "archiving as noise needs a reason"),
        ({"verb": "todo", "options": [], "link": "https://trusted.example"}, "link not in the email: https://trusted.example"),
        (
            {"verb": "todo", "options": [], "link": "https://vendor.example/pay/447"},
            "link not in the email: https://vendor.example/pay/447",
        ),
        ({"title": "Reply."}, "the title doesn't say what this email is"),
        ({"title": "Follow-up!"}, "the title doesn't say what this email is"),
    ],
)
def test_blank_or_partial_content_counts_as_missing(changes: dict[str, object], problem: str):
    assert problem in problems(proposal(**changes), BODY, HISTORY)


def test_whole_links_and_recipients_match_however_they_are_written():
    link = proposal(verb="todo", options=[], link="https://trusted.example.evil.test/path")
    recipient = proposal(verb="forward", options=[], draft="FYI", forward_to=" legal@EXAMPLE.com ")

    assert problems(link, BODY, HISTORY) == []
    assert problems(recipient, BODY, HISTORY) == []


def test_grounding_tolerates_reflowed_whitespace_but_nothing_else():
    reflowed = proposal(evidence=["Could we meet\nThursday at  3pm"])
    recased = proposal(evidence=["could we meet thursday at 3pm"])

    assert problems(reflowed, BODY, HISTORY) == []
    assert problems(recased, BODY, HISTORY) == ["evidence not in the email: 'could we meet thursday at 3pm'"]


def test_each_verb_is_satisfied_by_its_own_artifact():
    due = datetime(2026, 12, 1, tzinfo=UTC)
    satisfied = [
        proposal(draft="Sure, Thursday works.", options=[]),
        proposal(verb="forward", draft="FYI", options=[], forward_to="legal@example.com"),
        proposal(verb="digest", options=[], digest="Budget meeting request"),
        proposal(verb="snooze", options=[], due=due),
        proposal(verb="follow_up", options=[], due=due),
        proposal(verb="todo", options=[], link="https://vendor.example/pay/4471"),
        proposal(verb="todo", options=[], due=due),
        proposal(verb="archive_noise", options=[], noise_rationale="Automated notice"),
        proposal(verb="unsubscribe", options=[], noise_rationale="Bulk promotions"),
    ]

    assert [problems(each, BODY, HISTORY) for each in satisfied] == [[]] * len(satisfied)


async def test_a_valid_proposal_becomes_a_job_with_its_artifacts(test_db):
    """AC-3.1/AC-3.2: a created job's quotes are in the email and it carries a step-saving artifact."""
    source = message()
    await source.insert()
    job = to_job(source, proposal(), BODY, HISTORY)
    await job.insert()

    stored = await Job.get(job.id)
    assert stored is not None and not stored.ask_owner and stored.verb == "reply"
    assert all(quote in BODY for quote in stored.evidence)
    assert stored.artifacts.options == ["Thursday works", "Can't make it", "Later"]
    assert stored.message_ids == [source.id] and stored.owner_id == source.owner_id


async def test_a_failing_proposal_becomes_an_ask_owner_job_and_never_a_guess(test_db):
    """AC-3.2: no artifact → the ask-owner card instead; its content isn't shown as if it were valid."""
    ungrounded = proposal(evidence=["Invented quote"], draft="Sure!", options=[])
    source = message()
    await source.insert()
    job = to_job(source, ungrounded, BODY, HISTORY)
    await job.insert()

    assert job.ask_owner and job.suggested_verbs == ["reply"]
    assert job.problems == ["evidence not in the email: 'Invented quote'"]
    assert job.title == "Q4 budget review" and job.evidence == []
    assert job.artifacts.model_dump() == job.artifacts.model_validate({}).model_dump()


def test_titles_in_any_script_and_links_ending_in_punctuation_pass():
    body = BODY + "\nSee https://en.wikipedia.org/wiki/Function_(mathematics). It has the formula."
    japanese = proposal(title="予算会議について")
    wiki = proposal(verb="todo", options=[], link="https://en.wikipedia.org/wiki/Function_(mathematics)")

    shouting = proposal(verb="todo", options=[], link="HTTPS://Vendor.example/Pay")

    assert problems(japanese, body, HISTORY) == []
    assert problems(wiki, body, HISTORY) == []
    assert problems(shouting, body + "\nOr HTTPS://Vendor.example/Pay.", HISTORY) == []
