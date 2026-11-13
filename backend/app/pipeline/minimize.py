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
YEAR = re.compile(r"\b(?:19|20)\d\d\b")
QUOTED_LINE = re.compile(r"^>(?!=?[ \t]*\d).*$\n?", re.MULTILINE)  # "> 50 units" is prose, not a quote
SIGNATURE = re.compile(r"^-- $", re.MULTILINE)  # RFC 3676; a bare "--" is often a divider in the body
QUOTED_SIGNATURE = re.compile(r"^(?:> ?)+-- $")
QUOTE_MARKERS = "> "
# The IMAP plugin renders deeper HTML quotes at this depth too, so a run there can't tell a
# signature's lines from older history below it.
CAPPED_QUOTE_DEPTH = 8
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
        text = without_reply_history(text)
    text = without_signature(text, forwarded)
    # Quoted lines after an unquoted forward marker are the forwarded payload (HTML forwards quote it).
    marker = FORWARDED_BLOCK.search(text)
    payload_start = marker.start() if marker else len(text)
    own = QUOTED_LINE.sub("", without_attributions(text[:payload_start]))
    text = MOBILE_FOOTER.sub("", own + without_quoted_signatures(text[payload_start:]))
    text = URL.sub(lambda match: without_tracking(match.group()), text)
    return capped(re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.splitlines())).strip())


def without_reply_history(text: str) -> str:
    """Cuts Outlook-style history that starts above any explicit forward marker; headers inside a
    forwarded payload belong to it."""
    marker = FORWARDED_BLOCK.search(text)
    end = marker.start() if marker else len(text)
    starts = [match.start() for pattern in (OUTLOOK_HISTORY, ORIGINAL_MESSAGE) if (match := pattern.search(text, 0, end))]
    return text[: min(starts)] if starts else text


def without_attributions(text: str) -> str:
    """Drops "On <date>, <name> wrote:" lines that introduce a quote, line by line so hostile input stays linear."""
    lines, kept, index = text.split("\n"), [], 0
    while index < len(lines):
        following = lines[index + 1] if index + 1 < len(lines) else ""
        length = 1 if is_attribution(lines[index]) else 2 if is_wrapped_attribution(lines[index], following) else 0
        if length and introduces_quote(lines, index + length):
            index += length
        else:
            kept.append(lines[index])
            index += 1
    return "\n".join(kept)


def introduces_quote(lines: list[str], index: int) -> bool:
    """A real attribution is followed by the quoted history it introduces."""
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index < len(lines) and QUOTED_LINE.match(lines[index]) is not None


def is_attribution(line: str) -> bool:
    """Names the sender's address or the year; prose that merely ends in "wrote:" does neither."""
    line = line.rstrip()
    return line.startswith("On ") and line.endswith("wrote:") and ("@" in line or YEAR.search(line) is not None)


def is_wrapped_attribution(first: str, second: str) -> bool:
    """Only the long-header wrap that splits at the sender's <address>, so new content is never taken."""
    first, second = first.rstrip(), second.rstrip()
    split_at_address = first.endswith("<") or second.startswith("<")
    return first.startswith("On ") and split_at_address and second.endswith("wrote:")


def without_signature(text: str, forwarded: bool) -> str:
    """Drops each signature, from its delimiter up to the next forwarded block, which is content."""
    blocks = ANY_FORWARDED_BLOCK if forwarded else FORWARDED_BLOCK
    pieces, position = [], 0
    while (signature := SIGNATURE.search(text, position)) is not None:
        pieces.append(text[position : signature.start()])
        payload = blocks.search(text, signature.end())
        position = payload.start() if payload else len(text)
    return "".join(pieces) + text[position:]


def without_quoted_signatures(payload: str) -> str:
    """Drops each quoted "-- " delimiter in a forwarded payload with the contiguous lines at its quote
    depth. Only here: in a bottom-posted reply an answer can follow a quoted signature."""
    lines, kept, index = payload.split("\n"), [], 0
    while index < len(lines):
        depth = quote_depth(lines[index])
        if QUOTED_SIGNATURE.match(lines[index]) and depth < CAPPED_QUOTE_DEPTH:
            index = signature_end(lines, index + 1, depth)
        else:
            kept.append(lines[index])
            index += 1
    return "\n".join(kept)


def signature_end(lines: list[str], start: int, depth: int) -> int:
    """Where the run at the delimiter's depth ends, or earlier at a forwarded block inside it, which is content."""
    end = start
    while end < len(lines) and quote_depth(lines[end]) == depth:
        end += 1
    run = "\n".join(line.lstrip(QUOTE_MARKERS) for line in lines[start:end])
    block = ANY_FORWARDED_BLOCK.search(run)
    return start + run.count("\n", 0, block.start()) if block else end


def quote_depth(line: str) -> int:
    return line[: len(line) - len(line.lstrip(QUOTE_MARKERS))].count(">")


def without_tracking(match: str) -> str:
    """Drops tracking parameters as raw segments, so every other byte of the link survives."""
    url = match.rstrip(TRAILING_PUNCTUATION)
    prose = match[len(url) :]
    url, hash_mark, fragment = url.partition("#")  # a fragment is the page's own route, never tracking
    address, separator, query = url.partition("?")
    kept = [segment for segment in query.split("&") if not TRACKING_PARAMETER.match(segment)]
    return address + (separator if any(kept) else "") + "&".join(kept) + hash_mark + fragment + prose


def capped(text: str) -> str:
    if len(text) <= MINIMIZED_MAX_CHARACTERS:
        return text
    return text[: MINIMIZED_MAX_CHARACTERS - len(TRUNCATED)].rstrip() + TRUNCATED
