"""Minimize (spec §8.1): before a mail reaches the AI, keep only its new content (no quoted history,
signatures or tracking parameters) and cap its length. Runs in every privacy mode. Deterministic,
so the grounding check (§8.5) can match evidence quotes against the same text."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MINIMIZED_MAX_CHARACTERS = 8000
TRUNCATED = "\n[…truncated]"

# shortcut: English reply/forward conventions and RFC 3676 "-- " signatures only; add other languages or
# a learned signature detector when calibration (#92) shows history or signatures reaching proposals.
FORWARD_SUBJECT = re.compile(r"^\s*(?:fw|fwd)\s*:", re.IGNORECASE)
# Outlook replies: an optional separator, then a From/Sent header block over the older thread.
OUTLOOK_HISTORY = re.compile(
    r"^(?:-+ ?Original Message ?-+[ \t]*\n|_{8,}[ \t]*\n)?From:[^\n]*\nSent:", re.MULTILINE | re.IGNORECASE
)
ORIGINAL_MESSAGE = re.compile(r"^-+ ?Original Message ?-+[ \t]*$", re.MULTILINE | re.IGNORECASE)
ATTRIBUTION = re.compile(r"^On\b[^\n]*(?:\n[^\n]*)?\bwrote:[ \t]*$\n?", re.MULTILINE)
QUOTED_LINE = re.compile(r"^>.*$\n?", re.MULTILINE)
SIGNATURE = re.compile(r"^-- ?$", re.MULTILINE)
MOBILE_FOOTER = re.compile(
    r"^(?:Sent from my \w.*|Sent from (?:Mail|Outlook) for \w.*|Get Outlook for \w.*)$\n?", re.MULTILINE
)
URL = re.compile(r"https?://\S+")
TRACKING_PARAMETER = re.compile(r"^(?:utm_\w+|fbclid|gclid|mc_eid|mc_cid|_hsenc|_hsmi|mkt_tok)$", re.IGNORECASE)


def minimize(text: str, subject: str = "") -> str:
    """The new content of a mail body (`MessageDetail.text`). A forward's history is what was
    forwarded, so it is kept; Outlook marks replies and forwards alike, only the subject differs."""
    if not FORWARD_SUBJECT.match(subject):
        text = cut_at_first(text, (OUTLOOK_HISTORY, ORIGINAL_MESSAGE))
    text = cut_at_first(text, (SIGNATURE,))
    for pattern in (ATTRIBUTION, QUOTED_LINE, MOBILE_FOOTER):
        text = pattern.sub("", text)
    text = URL.sub(lambda match: without_tracking(match.group()), text)
    return capped(re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.splitlines())).strip())


def cut_at_first(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    starts = [match.start() for pattern in patterns if (match := pattern.search(text))]
    return text[: min(starts)] if starts else text


def without_tracking(url: str) -> str:
    parts = urlsplit(url)
    parameters = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(key, value) for key, value in parameters if not TRACKING_PARAMETER.match(key)]
    if len(kept) == len(parameters):
        return url  # untouched, so evidence quoting the link still matches
    return urlunsplit(parts._replace(query=urlencode(kept)))


def capped(text: str) -> str:
    if len(text) <= MINIMIZED_MAX_CHARACTERS:
        return text
    return text[: MINIMIZED_MAX_CHARACTERS - len(TRUNCATED)].rstrip() + TRUNCATED
