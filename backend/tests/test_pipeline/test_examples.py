# Example store and similarity retrieval (spec §4 Example, §8.4): past owner decisions come back as
# context for similar mail, scoped to their owner. Real MongoDB.
from datetime import UTC, datetime

from app.models.example import Example
from app.models.message import Message
from app.pipeline.examples import EXAMPLES_PER_PROPOSAL, record_example, similar_examples

OWNER = "owner-1"
RIDE = "Saturday long run is 18 miles from the boathouse at 7am. Reply if you're joining so I can plan water stops."


def inbox_message(subject: str, sender: str = "coach@runclub.example", owner_id: str = OWNER, list_id: str | None = None) -> Message:
    return Message.model_validate({
        "owner_id": owner_id, "plugin_id": "proton", "ref": f"in-{subject}", "message_id": f"<{subject}@x>",
        "sender": {"email": sender}, "to": [{"email": "frank@example.com"}], "cc": [],
        "date": datetime(2026, 11, 2, tzinfo=UTC), "subject": subject, "snippet": "", "list_id": list_id,
    })


async def test_an_example_stores_the_messages_features_and_the_owners_decision(test_db):
    message = inbox_message("Saturday long run", sender="Coach@RunClub.example", list_id="Run Club <club.runclub.example>")

    await record_example(message, f"{RIDE}\n\n-- \nCoach Dee", "reply", "ask_owner")

    [example] = await Example.find_all().to_list()
    assert (example.owner_id, example.sender, example.list_id) == (OWNER, "coach@runclub.example", "club.runclub.example")
    assert (example.subject, example.text, example.verb, example.source) == ("Saturday long run", RIDE, "reply", "ask_owner")


async def test_a_near_identical_message_retrieves_its_example(test_db):
    await record_example(inbox_message("Saturday long run: 18 miles"), RIDE, "reply", "ask_owner")

    found = await similar_examples(inbox_message("Saturday long run: 16 miles"), RIDE.replace("18", "16"))

    assert [(example.subject, example.verb) for example in found] == [("Saturday long run: 18 miles", "reply")]


async def test_an_unrelated_message_retrieves_nothing(test_db):
    await record_example(inbox_message("Saturday long run: 18 miles"), RIDE, "reply", "ask_owner")

    found = await similar_examples(
        inbox_message("Invoice 4471 due November 20", sender="billing@vendor.example"),
        "Your invoice 4471 for $240.00 is due on November 20, 2026. Pay online at https://vendor.example/pay/4471",
    )

    assert found == []


async def test_another_owners_examples_never_come_back(test_db):
    await record_example(inbox_message("Saturday long run: 18 miles", owner_id="owner-2"), RIDE, "reply", "correction")

    assert await similar_examples(inbox_message("Saturday long run: 18 miles"), RIDE) == []


async def test_at_most_k_examples_come_back_most_similar_first(test_db):
    await record_example(inbox_message("Saturday long run: 18 miles"), RIDE, "digest", "correction")
    for miles in range(10, 10 + EXAMPLES_PER_PROPOSAL + 2):
        from_the_trailhead = RIDE.replace("18", str(miles)).replace("boathouse", "trailhead")
        await record_example(inbox_message(f"Saturday long run: {miles} miles"), from_the_trailhead, "reply", "ask_owner")

    found = await similar_examples(inbox_message("Saturday long run: 18 miles"), RIDE)

    assert len(found) == EXAMPLES_PER_PROPOSAL
    assert (found[0].subject, found[0].verb) == ("Saturday long run: 18 miles", "digest")


async def test_the_same_sender_alone_is_not_similar_enough(test_db):
    await record_example(inbox_message("Saturday long run: 18 miles"), RIDE, "reply", "ask_owner")

    found = await similar_examples(inbox_message("Club dues"), "Annual dues of $40 are payable by card before January 31.")

    assert found == []


async def test_the_same_list_counts_toward_similarity(test_db):
    """A list's issues share little wording week to week; the shared stream makes up the difference."""
    newsletter = "Weekly Design <weekly.example>"
    await record_example(
        inbox_message("This week in product design", sender="news@weekly.example", list_id=newsletter),
        "Five essays on onboarding flows, a talk on design systems, and our pick of the week's tools.", "digest", "correction",
    )
    next_issue = "A long read on research, an interview with a founder, and two new podcasts."

    from_the_list = await similar_examples(
        inbox_message("This week in product design", sender="news@weekly.example", list_id=newsletter), next_issue
    )
    elsewhere = await similar_examples(inbox_message("This week in product design", sender="news@other.example"), next_issue)

    assert [example.verb for example in from_the_list] == ["digest"]
    assert elsewhere == []


async def test_an_example_reads_as_one_short_line(test_db):
    example = await record_example(inbox_message("Saturday long run"), RIDE * 20, "reply", "ask_owner")

    summary = example.summary()

    assert summary.startswith('From coach@runclub.example, subject "Saturday long run": Saturday long run is 18 miles')
    assert summary.endswith("-> reply") and "\n" not in summary and len(summary) < 400
