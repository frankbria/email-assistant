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
FORWARDED_BLOCK = re.compile(r"^(?:-+ ?Forwarded message ?-+|Begin forwarded message:)", re.MULTILINE | re.IGNORECASE)
ORIGINAL_MESSAGE = re.compile(r"^-+ ?Original Message ?-+[ \t]*$", re.MULTILINE | re.IGNORECASE)
# One alternation finds the earliest block in a single scan (separate searches would be quadratic).
ANY_FORWARDED_BLOCK = re.compile(
    "|".join(pattern.pattern for pattern in (FORWARDED_BLOCK, OUTLOOK_HISTORY, ORIGINAL_MESSAGE)),
    re.MULTILINE | re.IGNORECASE,
)
# An attribution names the sender's address or the year; prose that merely ends in "wrote:" does not.
# A wrapped one continues onto a second line, which is never itself a new "On …" line.
ATTRIBUTION = re.compile(
    r"^On\b[^\n]*(?:\n(?!On\b)[^\n]*)?@[^\n]*\bwrote:[ \t]*$\n?|^On\b[^\n]*\b(?:19|20)\d\d\b[^\n]*\bwrote:[ \t]*$\n?",
    re.MULTILINE,
)
QUOTED_LINE = re.compile(r"^>(?!=?[ \t]*\d).*$\n?", re.MULTILINE)  # "> 50 units" is prose, not a quote
SIGNATURE = re.compile(r"^-- $", re.MULTILINE)  # RFC 3676; a bare "--" is often a divider in the body
MOBILE_FOOTER = re.compile(
    r"^(?:Sent from my (?:iPhone|iPad|Android|Galaxy|BlackBerry|Pixel|mobile|phone)\b.*"
    r"|Sent from (?:Mail|Outlook) for \w.*|Get Outlook for \w.*)$\n?",
    re.MULTILINE | re.IGNORECASE,
)
URL = re.compile(r"https?://[^\s<>]+")
TRAILING_PUNCTUATION = ".,;:!?)]'\""  # prose around a link, not part of it
TRACKING_PARAMETER = re.compile(r"^(?:utm_\w+|fbclid|gclid|mc_eid|mc_cid|_hsenc|_hsmi|mkt_tok)(?:=|$)", re.IGNORECASE)


def minimize(text: str, subject: str = "") -> str:
    """The new content of a mail body (`MessageDetail.text`). A forward's history is what was
    forwarded, so it is kept; Outlook marks replies and forwards alike, only the subject differs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    forwarded = bool(FORWARD_SUBJECT.match(subject))
    if not forwarded:
        text = cut_at_first(text, (OUTLOOK_HISTORY, ORIGINAL_MESSAGE))
    text = without_signature(text, forwarded)
    for pattern in (ATTRIBUTION, QUOTED_LINE, MOBILE_FOOTER):
        text = pattern.sub("", text)
    text = URL.sub(lambda match: without_tracking(match.group()), text)
    return capped(re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.splitlines())).strip())


def cut_at_first(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    starts = [match.start() for pattern in patterns if (match := pattern.search(text))]
    return text[: min(starts)] if starts else text


def without_signature(text: str, forwarded: bool) -> str:
    """Drops each signature, from its delimiter up to the next forwarded block, which is content."""
    blocks = ANY_FORWARDED_BLOCK if forwarded else FORWARDED_BLOCK
    pieces, position = [], 0
    while (signature := SIGNATURE.search(text, position)) is not None:
        pieces.append(text[position : signature.start()])
        payload = blocks.search(text, signature.end())
        position = payload.start() if payload else len(text)
    return "".join(pieces) + text[position:]


def without_tracking(match: str) -> str:
    """Drops tracking parameters as raw segments, so every other byte of the link survives."""
    url = match.rstrip(TRAILING_PUNCTUATION)
    prose = match[len(url) :]
    address, separator, query = url.partition("?")
    query, hash_mark, fragment = query.partition("#")
    kept = [segment for segment in query.split("&") if not TRACKING_PARAMETER.match(segment)]
    return address + (separator if any(kept) else "") + "&".join(kept) + hash_mark + fragment + prose


def capped(text: str) -> str:
    if len(text) <= MINIMIZED_MAX_CHARACTERS:
        return text
    return text[: MINIMIZED_MAX_CHARACTERS - len(TRUNCATED)].rstrip() + TRUNCATED
