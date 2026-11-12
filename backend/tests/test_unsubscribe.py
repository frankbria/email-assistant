# Unsubscribe targets from List-Unsubscribe (RFC 2369) and strict mailto parsing (RFC 6068). The header is written
# by whoever sent the mail, so anything but a plain https link or a single-address mailto is never offered.
import ast
from pathlib import Path

import pytest
from mailbox_contract import Header

from app.unsubscribe import UnsubscribeMail, unsubscribe_mail, unsubscribe_target


def header(value: str) -> list[Header]:
    return [Header(name="Received", value="from mx1"), Header(name="List-Unsubscribe", value=value)]


@pytest.mark.parametrize(
    ("value", "target"),
    [
        ("<mailto:leave@shop.example>, <https://shop.example/u?id=7>", "https://shop.example/u?id=7"),
        ("<mailto:leave@shop.example?subject=unsubscribe>", "mailto:leave@shop.example?subject=unsubscribe"),
        ("<https://shop.example/u\r\n ?id=7>", "https://shop.example/u?id=7"),  # a folded header: whitespace is ignored
        ("<javascript:alert(1)>, <mailto:leave@shop.example>", "mailto:leave@shop.example"),
        ("<http://shop.example/u>, <mailto:leave@shop.example>", "mailto:leave@shop.example"),  # plain http isn't offered
        ("<https://shop.example@internal.example/u>", None),  # credentials hide the real host
        ("<https://shop.example:99999/u>, <mailto:leave@shop.example>", "mailto:leave@shop.example"),  # port out of range
        ("<data:text/html,hi>, <ftp://shop.example/u>", None),
        ("<mailto:a@shop.example,b@shop.example>", None),
        ("https://shop.example/u", None),  # not in angle brackets: not RFC 2369
        ("", None),
    ],
)
def test_the_target_is_the_https_link_else_the_mailto_and_nothing_unsafe(value: str, target: str | None):
    assert unsubscribe_target(header(value)) == target


def test_mail_without_the_header_has_no_target():
    assert unsubscribe_target([Header(name="List-Id", value="<deals.shop.example>")]) is None


@pytest.mark.parametrize(
    ("target", "mail"),
    [
        ("mailto:leave@shop.example", UnsubscribeMail("leave@shop.example", "unsubscribe", "unsubscribe")),
        (
            "MAILTO:leave%2Bdeals@shop.example?Subject=Stop%20please&body=list%3D7%0D%0Athanks",
            UnsubscribeMail("leave+deals@shop.example", "Stop please", "list=7\r\nthanks"),
        ),
    ],
)
def test_a_mailto_gives_its_one_address_subject_and_body(target: str, mail: UnsubscribeMail):
    assert unsubscribe_mail(target) == mail


@pytest.mark.parametrize(
    "target",
    [
        "mailto:leave@shop.example?subject=hi%0D%0ABcc:%20victim@else.example",  # header injection through the subject
        "mailto:leave@shop.example%0D%0ABcc:victim@else.example",
        "mailto:leave@shop.example,victim@else.example",
        "mailto:leave@shop.example?to=victim@else.example",
        "mailto:leave@shop.example?cc=victim@else.example",
        "mailto:leave@shop.example?bcc=victim@else.example",
        "mailto:leave@shop.example?subject=a&subject=b",
        "mailto:leave@shop.example?subject",
        "mailto:Leave <leave@shop.example>",
        "mailto:?subject=unsubscribe",
        "mailto:leave",
        "https://shop.example/u",
    ],
)
def test_a_mailto_that_could_send_elsewhere_or_inject_headers_is_refused(target: str):
    with pytest.raises(ValueError):
        unsubscribe_mail(target)


def test_nothing_on_the_unsubscribe_path_can_make_an_http_request():
    """The server never fetches a link from mail (SSRF): the owner's browser opens https targets."""
    app = Path(__file__).resolve().parents[1] / "app"
    http_clients = {"httpx", "requests", "aiohttp", "urllib.request", "http.client", "socket"}
    for module in ("unsubscribe.py", "executor.py", "api/routers/jobs.py"):
        tree = ast.parse((app / module).read_text())
        imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not {name for name in imported if name.split(".")[0] in http_clients or name in http_clients}, module
