"""Minimize (spec §8.1): before a mail reaches the AI, keep only its new content (no quoted history,
signatures or tracking parameters) and cap its length. Runs in every privacy mode. Deterministic,
so the grounding check (§8.5) can match evidence quotes against the same text."""

import re

MINIMIZED_MAX_CHARACTERS = 8000
TRUNCATED = "\n[…truncated]"

# When unsure, history or a signature leaks rather than new content being lost: the AI acting on
# missing information costs more than a few extra tokens. Hence the narrow patterns below.
# shortcut: English reply/forward conventions and RFC 3676 "-- " signatures only; add other languages or
# a learned signature detector when calibration (#92) shows history or signatures reaching proposals.
FORWARD_SUBJECT = re.compile(r"^\s*(?:fw|fwd)\s*:", re.IGNORECASE)
# Outlook replies put the older thread under a From/Sent block, or From/Date after a separator line;
# a bare From/Date pair also occurs in real content (a flight notice), so that alone cuts nothing.
OUTLOOK_HISTORY = re.compile(
    r"^(?:-+ ?Original Message ?-+[ \t]*\n|_{8,}[ \t]*\n)?From:[^\n]*\nSent:|^_{8,}[ \t]*\nFrom:[^\n]*\nDate:",
    re.MULTILINE | re.IGNORECASE,
)
ORIGINAL_MESSAGE = re.compile(r"^-+ ?Original Message ?-+[ \t]*$", re.MULTILINE | re.IGNORECASE)
# An attribution names the sender's address; prose that merely ends in "wrote:" does not.
ATTRIBUTION = re.compile(r"^On\b[^\n]*(?:\n[^\n]*)?@[^\n]*\bwrote:[ \t]*$\n?", re.MULTILINE)
QUOTED_LINE = re.compile(r"^>(?!=?[ \t]*\d).*$\n?", re.MULTILINE)  # "> 50 units" is prose, not a quote
SIGNATURE = re.compile(r"^-- $", re.MULTILINE)  # RFC 3676; a bare "--" is often a divider in the body
MOBILE_FOOTER = re.compile(
    r"^(?:Sent from my (?:iPhone|iPad|Android|Galaxy|BlackBerry|Pixel|mobile|phone)\b.*"
    r"|Sent from (?:Mail|Outlook) for \w.*|Get Outlook for \w.*)$\n?",
    re.MULTILINE | re.IGNORECASE,
)
URL = re.compile(r"https?://\S+?(?=[.,;:!?)\]'\"]*(?:\s|$))")  # trailing prose punctuation is not the link's
TRACKING_PARAMETER = re.compile(r"^(?:utm_\w+|fbclid|gclid|mc_eid|mc_cid|_hsenc|_hsmi|mkt_tok)(?:=|$)", re.IGNORECASE)


def minimize(text: str, subject: str = "") -> str:
    """The new content of a mail body (`MessageDetail.text`). A forward's history is what was
    forwarded, so it is kept; Outlook marks replies and forwards alike, only the subject differs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
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
    """Drops tracking parameters as raw segments, so every other byte of the link survives."""
    address, separator, query = url.partition("?")
    query, hash_mark, fragment = query.partition("#")
    kept = [segment for segment in query.split("&") if not TRACKING_PARAMETER.match(segment)]
    return address + (separator if any(kept) else "") + "&".join(kept) + hash_mark + fragment


def capped(text: str) -> str:
    if len(text) <= MINIMIZED_MAX_CHARACTERS:
        return text
    return text[: MINIMIZED_MAX_CHARACTERS - len(TRUNCATED)].rstrip() + TRUNCATED
