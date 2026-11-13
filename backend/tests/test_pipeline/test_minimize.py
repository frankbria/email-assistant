# Minimize stage (spec §8.1, AC-R.2): what reaches the AI is the new content only.
import time

import pytest
from imap_mailbox.mailbox import html_to_text

from app.pipeline.minimize import MINIMIZED_MAX_CHARACTERS, TRUNCATED, minimize
from tests.fixtures.minimize_corpus import CORPUS, MinimizeCase


@pytest.mark.parametrize("case", CORPUS, ids=[case.name for case in CORPUS])
def test_minimized_text_keeps_the_new_content_and_drops_history_signatures_and_tracking(case: MinimizeCase):
    minimized = minimize(case.text, case.subject)

    for phrase in case.kept:
        assert phrase in minimized
    for phrase in case.removed:
        assert phrase not in minimized


@pytest.mark.parametrize("case", CORPUS, ids=[case.name for case in CORPUS])
def test_minimizing_twice_changes_nothing(case: MinimizeCase):
    """Grounding (§8.5) re-checks quotes against the minimized text, so it must be stable."""
    once = minimize(case.text, case.subject)

    assert minimize(once, case.subject) == once


def test_long_mail_is_capped_with_a_visible_marker():
    minimized = minimize("word " * MINIMIZED_MAX_CHARACTERS)

    assert len(minimized) <= MINIMIZED_MAX_CHARACTERS
    assert minimized.endswith(TRUNCATED)


def test_blank_runs_collapse_and_empty_mail_stays_empty():
    assert minimize("first\n\n\n\n\nsecond\n") == "first\n\nsecond"
    assert minimize("") == ""
    assert minimize("> only quoted history\n") == ""


def test_a_mail_with_thousands_of_signatures_and_forwards_neither_crashes_nor_keeps_a_signature():
    nested = minimize("-- \nsignature\n---------- Forwarded message ---------\nbody\n" * 5000, "Fwd: chain")

    assert "signature" not in nested and nested.count("body") > 0


def test_untrusted_punctuation_runs_after_a_link_stay_linear():
    """A quadratic scan here lets one large mail tie up the pipeline (50,000 dots took minutes)."""
    started = time.perf_counter()

    minimize("https://example.com/" + "." * 50_000 + "a")

    assert time.perf_counter() - started < 2


@pytest.mark.parametrize(
    "hostile", ["On " + "@" * 50_000, ("On " + "a" * 1000 + "\n") * 2000 + "On a@b wrote:"], ids=["at-signs", "many-on-lines"]
)
def test_untrusted_attribution_look_alikes_stay_linear(hostile: str):
    started = time.perf_counter()

    minimize(hostile)

    assert time.perf_counter() - started < 2


def test_an_html_forward_keeps_the_forwarded_text_without_its_senders_signature():
    html = (
        "<div>Please pay this.</div><div>Begin forwarded message:</div><blockquote><div>Invoice 4471 is due Friday.</div>"
        "<div>-- </div><div>Ana Smith | +1 555 0100</div></blockquote>"
    )

    minimized = minimize(html_to_text(html), "Fwd: Invoice")

    assert "Invoice 4471 is due Friday." in minimized
    assert "Ana Smith" not in minimized and "555 0100" not in minimized


def test_untrusted_deep_quoting_in_a_forward_stays_linear():
    started = time.perf_counter()

    minimize("Begin forwarded message:\n" + ("> " * 50_000 + "-- x\n") * 20, "Fwd: chain")

    assert time.perf_counter() - started < 2
