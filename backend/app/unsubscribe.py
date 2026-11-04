"""Unsubscribing (spec §4: never_auto, "links in email are untrusted"). The target comes from the mail's
List-Unsubscribe header (RFC 2369), is shown to the owner in full, and is acted on only on their tap. This server
never fetches a link from mail (a sender could aim it at internal services): the owner's own browser opens an
https target, and a mailto target goes out through the owner's mailbox to its one address.
shortcut: RFC 8058 one-click unsubscribe is a POST this server would have to make, so it isn't offered; the
owner's browser opens the page instead, which may ask for one more click. Add it behind an outbound allow-list
if owners ask for it."""

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from mailbox_contract import Header

BRACKETED = re.compile(r"<([^<>]*)>")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
ATOM = r"[^\s\x00-\x1f\x7f@<>,;:\"()\[\]\\]+"
ADDRESS = re.compile(rf"{ATOM}@{ATOM}")
DEFAULT_REQUEST = "unsubscribe"


@dataclass(frozen=True)
class UnsubscribeMail:
    address: str
    subject: str
    body: str


def unsubscribe_target(headers: list[Header]) -> str | None:
    """The header's https link, else its mailto; any other scheme, or a target that fails the checks, isn't offered."""
    value = next((header.value for header in headers if header.name.lower() == "list-unsubscribe"), "")
    targets = ["".join(found.split()) for found in BRACKETED.findall(value)]  # RFC 2369: whitespace in a URL is ignored
    return next((target for target in targets if is_https(target)), None) or next(
        (target for target in targets if is_mailto(target)), None
    )


def is_https(target: str) -> bool:
    """Credentials (https://shop.example@internal.example/) would hide the real host from the owner."""
    try:
        parts = urlsplit(target)
        return parts.scheme.lower() == "https" and bool(parts.hostname) and parts.username is None and not CONTROL.search(target)
    except ValueError:  # e.g. an unbalanced IPv6 bracket
        return False


def is_mailto(target: str) -> bool:
    try:
        unsubscribe_mail(target)
        return True
    except ValueError:
        return False


def unsubscribe_mail(target: str) -> UnsubscribeMail:
    """RFC 6068, strictly: one address, and at most a subject and a body. Any other field (to, cc, bcc) would send
    the owner's mail somewhere else, and a line break in the address or subject would inject headers."""
    scheme, _, rest = target.partition(":")
    if scheme.lower() != "mailto":
        raise ValueError("an unsubscribe email needs a mailto target")
    encoded_address, _, query = rest.partition("?")
    address = unquote(encoded_address)
    if not ADDRESS.fullmatch(address):
        raise ValueError("the unsubscribe target isn't one email address")
    fields: dict[str, str] = {}
    for pair in query.split("&") if query else []:
        name, separator, value = pair.partition("=")
        name = unquote(name).lower()
        if not separator or name not in ("subject", "body") or name in fields:
            raise ValueError("the unsubscribe target asks for more than a subject and a body")
        fields[name] = unquote(value)
    subject = fields.get("subject") or DEFAULT_REQUEST
    if CONTROL.search(subject):
        raise ValueError("the unsubscribe target's subject has a line break")
    return UnsubscribeMail(address=address, subject=subject, body=fields.get("body") or DEFAULT_REQUEST)
