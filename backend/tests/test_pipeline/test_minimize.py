# Minimize stage (spec §8.1, AC-R.2): what reaches the AI is the new content only.
import pytest

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
