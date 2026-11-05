# HTML-only mail → the plain text the plugin returns (MessageDetail.text and the snippet).
import time

import pytest

from app.pipeline.minimize import minimize
from imap_mailbox.mailbox import html_to_text


@pytest.mark.parametrize(
    ("html", "text"),
    [
        ("<p>Hello <i>there</i></p>", "Hello there"),
        ("first<br>second<br/>third", "first\nsecond\nthird"),
        ("<div>Approved.</div>\n<blockquote>Cancel the purchase.</blockquote>", "Approved.\n> Cancel the purchase."),
        (
            "<p>Yes</p><blockquote><p>Cancel <b>the</b> purchase</p><blockquote>older</blockquote></blockquote><p>Thanks</p>",
            "Yes\n> Cancel the purchase\n> > older\nThanks",
        ),
        ("<head><style>p { color: red }</style><script>track()</script></head><p>Body</p>", "Body"),
        (
            "<html><head><title>Invoice</title><body><p>Please pay invoice 4471 by Friday.</p></body></html>",
            "Please pay invoice 4471 by Friday.",
        ),
    ],
    ids=["inline tags", "line breaks", "quote", "nested quotes", "style and script", "head never closed"],
)
def test_html_becomes_text_with_quotes_marked_like_plain_text_mail(html: str, text: str):
    assert html_to_text(html) == text


def test_quoted_history_in_an_html_only_reply_never_reaches_the_ai():
    html = "<div>Approved.</div><div>On Mon, Nov 2, 2026, Ana &lt;ana@example.com&gt; wrote:</div><blockquote>Cancel the purchase.</blockquote>"

    assert minimize(html_to_text(html)) == "Approved."


def test_an_html_forward_keeps_its_quoted_payload():
    html = "<div>Please pay the forwarded invoice.</div><div>Begin forwarded message:</div><blockquote>Invoice 4471 is due Friday.</blockquote>"

    assert "Invoice 4471 is due Friday." in minimize(html_to_text(html), "Fwd: Invoice")


def test_an_html_signature_is_still_recognized():
    html = "<div>Please approve invoice 4471.</div><div>-- </div><div>Ana Smith</div><div>Sales Director | +1 555 0100</div>"

    assert minimize(html_to_text(html)) == "Please approve invoice 4471."


def test_many_inline_elements_on_one_line_stay_linear():
    """Untrusted HTML: a quadratic join here stalls message retrieval (200,000 spans took 17 s)."""
    started = time.perf_counter()

    text = html_to_text("<span>abcdefghij</span>" * 200_000)

    assert time.perf_counter() - started < 3 and len(text) == 2_000_000


def test_deeply_nested_quotes_cannot_blow_up_the_text():
    """Markers per line are capped: 5,000 nested quotes x 5,000 lines once produced 50 MB from 85 KB."""
    text = html_to_text("<blockquote>" * 5_000 + "x<br>" * 5_000)

    assert len(text) < 200_000 and text.startswith("> > ")
