# HTML-only mail → the plain text the plugin returns (MessageDetail.text and the snippet).
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
    ],
    ids=["inline tags", "line breaks", "quote", "nested quotes", "style and script"],
)
def test_html_becomes_text_with_quotes_marked_like_plain_text_mail(html: str, text: str):
    assert html_to_text(html) == text


def test_quoted_history_in_an_html_only_reply_never_reaches_the_ai():
    html = "<div>Approved.</div><div>On Mon, Nov 2, 2026, Ana &lt;ana@example.com&gt; wrote:</div><blockquote>Cancel the purchase.</blockquote>"

    assert minimize(html_to_text(html)) == "Approved."
