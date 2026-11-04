"""Example store and retrieval (spec §4 Example, §8.4): the owner's past decisions, and those most
similar to a new message for its proposal prompt. Corrections, ask-owner choices and restores
(#83-#85) record them through record_example."""

import re

from app.models.example import Example, ExampleSource
from app.models.job import Verb
from app.models.message import Message
from app.models.rule import rule_key
from app.pipeline.minimize import minimize

EXAMPLES_PER_PROPOSAL = 3
STORED_TEXT_CHARACTERS = 1000
CANDIDATES = 500
MINIMUM_SIMILARITY = 0.3
SAME_STREAM_BONUS = 0.2  # a sender's or list's issues share few words but usually get the same handling
WORD = re.compile(r"[a-z0-9]{3,}")


async def record_example(message: Message, body: str, verb: Verb, source: ExampleSource) -> Example:
    """Stores the owner's decision on `message`. `body` is its `MessageDetail.text`, or its snippet
    when the full text wasn't fetched."""
    example = Example(
        owner_id=message.owner_id,
        sender=rule_key("sender", message.sender.email),
        list_id=rule_key("list_id", message.list_id) if message.list_id else None,
        subject=message.subject,
        text=minimize(body, message.subject)[:STORED_TEXT_CHARACTERS],
        verb=verb,
        source=source,
    )
    return await example.insert()


async def similar_examples(message: Message, body: str) -> list[Example]:
    """The owner's examples most similar to this message, most similar first, at most
    EXAMPLES_PER_PROPOSAL and none below MINIMUM_SIMILARITY.
    shortcut: word-overlap (Jaccard) over the owner's latest CANDIDATES examples misses paraphrases and
    older history; move to embeddings or a text index when calibration (#92) shows missed examples."""
    words = words_of(message.subject, minimize(body, message.subject)[:STORED_TEXT_CHARACTERS])
    sender = rule_key("sender", message.sender.email)
    list_id = rule_key("list_id", message.list_id) if message.list_id else None
    candidates = await Example.find(Example.owner_id == message.owner_id).sort("-created_at").limit(CANDIDATES).to_list()
    scored = []
    for candidate in candidates:
        theirs = words_of(candidate.subject, candidate.text)
        overlap = len(words & theirs) / len(words | theirs) if words | theirs else 0.0
        same_stream = candidate.list_id == list_id if list_id else candidate.sender == sender and not candidate.list_id
        scored.append((overlap + (SAME_STREAM_BONUS if same_stream else 0.0), candidate))
    # sorted() is stable, so among equal scores the most recent decision comes first.
    ranked = sorted(scored, key=lambda pair: pair[0], reverse=True)
    return [candidate for score, candidate in ranked if score >= MINIMUM_SIMILARITY][:EXAMPLES_PER_PROPOSAL]


def words_of(subject: str, text: str) -> set[str]:
    return set(WORD.findall(f"{subject} {text}".lower()))
