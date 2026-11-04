# The redaction stage (spec §8.2): personal details become typed placeholders before content leaves the server, and
# placeholders in the AI's answer become the real values again. Pure text: no services needed.
from datetime import UTC, datetime

import pytest

from app.pipeline.proposal import Proposal
from app.pipeline.redact import Redaction
from app.services.ai_provider import AIProposalError

MAIL = """Hi Frank,

Ana Lopez here (ana.lopez@acme.example). Call me on (555) 123-4567 or +44 20 7946 0958.
The invoice is at https://billing.acme.example/inv/42?u=frank and www.acme.example/help.
Card 4111 1111 1111 1111, account 12345678901, IBAN GB82WEST12345698765432.
Your verification code is 482913.

Best regards,
Ana"""


def test_every_kind_of_personal_detail_becomes_a_typed_placeholder():
    redacted = Redaction(["Ana Lopez"]).redact(MAIL)

    for real in ("Frank", "Ana", "Lopez", "ana.lopez@acme.example", "(555) 123-4567", "+44 20 7946 0958",
                 "https://billing.acme.example", "www.acme.example", "4111 1111 1111 1111", "12345678901",
                 "GB82WEST12345698765432", "482913"):
        assert real not in redacted, real
    for placeholder in ("PERSON_1", "EMAIL_1", "PHONE_1", "PHONE_2", "URL_1", "URL_2", "ACCOUNT_1", "CODE_1"):
        assert placeholder in redacted, placeholder


def test_restoring_the_redacted_text_gives_back_the_original():
    redaction = Redaction(["Ana Lopez"])

    assert redaction.restore(redaction.redact(MAIL)) == MAIL


def test_the_same_value_always_gets_the_same_placeholder():
    redaction = Redaction([])

    assert redaction.redact("a@x.example, then a@x.example") == "EMAIL_1, then EMAIL_1"
    assert redaction.redact("again a@x.example; b@x.example") == "again EMAIL_1; EMAIL_2"


def test_dates_times_and_ordinary_numbers_are_left_alone():
    text = "Date: 2026-11-04T10:00:00+00:00 — meet at 3pm on 12/05, room 101, budget 2,500 in Q4 2026."

    assert Redaction([]).redact(text) == text


def test_names_are_matched_as_whole_words_with_their_case():
    redacted = Redaction(["Will Smith"]).redact("Will said he will call Smithers and Will Smith.")

    assert redacted == "PERSON_2 said he will call Smithers and PERSON_1."


def test_a_placeholder_already_in_the_mail_is_never_reused_or_restored_to_something_else():
    redaction = Redaction([])

    redacted = redaction.redact("Literal EMAIL_1 and real a@x.example")

    assert redacted == "Literal EMAIL_1 and real EMAIL_2"
    assert redaction.restore("EMAIL_1 EMAIL_2") == "EMAIL_1 a@x.example"


def test_every_text_field_of_a_proposal_is_restored():
    redaction = Redaction(["Ana Lopez"])
    redaction.redact("Ana Lopez, ana@acme.example, https://acme.example/pay")
    proposal = Proposal(
        needs_owner=False, verb="todo", title="Pay PERSON_1's invoice", evidence=["pay at URL_1"], draft="Hi PERSON_1",
        options=["Yes, PERSON_1"], forward_to="EMAIL_1", link="URL_1", due=datetime(2026, 11, 5, tzinfo=UTC), confidence=0.8,
    )

    restored = redaction.restore_model(proposal)

    assert (restored.title, restored.evidence, restored.draft) == ("Pay Ana Lopez's invoice", ["pay at https://acme.example/pay"], "Hi Ana Lopez")
    assert (restored.options, restored.forward_to, restored.link) == (["Yes, Ana Lopez"], "ana@acme.example", "https://acme.example/pay")
    assert restored.due == proposal.due


def test_links_without_a_scheme_and_national_phone_numbers_are_caught():
    text = "Pay at acme.example/pay/42 or bit.ly/Xy12, see acme.com. Ring 020 7946 0958, 07700 900123 or 06 12 34 56 78."

    redacted = Redaction([]).redact(text)

    for real in ("acme.example", "bit.ly", "acme.com", "020 7946 0958", "07700 900123", "06 12 34 56 78"):
        assert real not in redacted, real


def test_a_word_like_code_or_pin_never_eats_a_date_and_european_dates_are_no_phones():
    text = "I'll pin this down by 2026-12-31; code word by 2026-12-31; meet 05.12.2026 or 05-12-2026, file report.pdf."

    assert Redaction([]).redact(text) == text


def test_a_link_with_parentheses_restores_exactly():
    redaction = Redaction([])
    text = "See https://en.wikipedia.org/wiki/Function_(math) for more."

    redacted = redaction.redact(text)

    assert "wikipedia" not in redacted and redaction.restore(redacted) == text


def test_greeting_and_sign_off_names_with_accents_or_apostrophes_and_only_one_word_after_a_greeting():
    redacted = Redaction([]).redact("Hi José Please find it attached, Please.\n\nRegards,\n\nSeán O'Brien")

    assert "José" not in redacted and "Seán" not in redacted and "O'Brien" not in redacted
    assert redacted.count("Please") == 2


def test_a_placeholder_the_ai_made_up_is_refused_rather_than_shown_to_the_owner():
    redaction = Redaction([])
    redaction.redact("Literal PERSON_4 and a@x.example")

    assert redaction.restore("PERSON_4 EMAIL_1") == "PERSON_4 a@x.example"
    with pytest.raises(AIProposalError):
        redaction.restore("Hi PERSON_9")


def test_an_american_express_number_in_its_four_six_five_groups_is_redacted():
    redacted = Redaction([]).redact("Card: 3782 822463 10005, or 3782-822463-10005.")

    assert "822463" not in redacted and "10005" not in redacted


def test_a_link_that_carries_an_email_address_is_restored_whole():
    """The email is replaced first, so the link's placeholder stands for text holding EMAIL_n: both must come back."""
    link = "https://example.com/pay?email=ana@example.com"
    redaction = Redaction([])
    redacted = redaction.redact(f"Pay here: {link}")

    assert "ana@example.com" not in redacted
    assert redaction.restore(redacted) == f"Pay here: {link}"
