"""Redaction stage (spec §8.2), redacted_cloud only: names, email addresses, URLs, account and card numbers, one-time
codes and phone numbers become typed placeholders (`PERSON_1`, `URL_2`, …) before anything leaves the server. The
mapping stays here; `restore` swaps placeholders in the AI's answer back to the real values.
shortcut: deterministic regexes plus names known from headers and greeting / sign-off lines; a name that appears only
mid-sentence and in no header (e.g. "ask Maria about it") goes through. Move to an NER model (e.g. Presidio + spaCy)
if owners need that, at the cost of a much larger image."""

import re
from collections.abc import Iterable
from typing import TypeVar

from pydantic import BaseModel

from app.services.ai_provider import AIProposalError

ModelT = TypeVar("ModelT", bound=BaseModel)

PLACEHOLDER = re.compile(r"\b(?:PERSON|EMAIL|PHONE|URL|ACCOUNT|CODE)_\d+\b")
# Like validate.URL: anything up to whitespace or <>, less the prose punctuation after it, so a restored link passes whole_link.
# A balanced "(...)" may end it (…/Function_(math)); a lone ")" is the prose around the link.
URL_REST = r"(?:[^\s<>()]|\([^\s<>()]*\))*(?:\([^\s<>()]*\)|[^\s<>.,;:!?()\]'\"])"
DOMAIN = r"(?<![\w@.-])(?:[a-z0-9-]+\.)+"
BARE_TLDS = "com|org|net|edu|gov|io|co|uk|us|ca|de|fr|es|it|nl|au|ly|me|app|dev|info|biz"
# Most specific first: an email's or URL's digits are never read as a phone or an account.
PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    # With a scheme or www., a bare domain with a path (bit.ly/x), or a bare domain on a common TLD (acme.com).
    ("URL", re.compile(
        rf"(?<![\w@.-])(?:https?://|www\.){URL_REST}|{DOMAIN}[a-z]{{2,}}/{URL_REST}|{DOMAIN}(?:{BARE_TLDS})\b(?![.-]?\w)(?:[?#]{URL_REST})?",
        re.IGNORECASE,
    )),
    # IBANs (whole, also in groups of four) before card numbers (groups of four, or Amex 4-6-5) and long digit runs.
    ("ACCOUNT", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b|\b\d{4}(?:[ -]\d{4}){2,3}\b|\b\d{4}[ -]\d{6}[ -]\d{5}\b|\b\d{8,19}\b")),
    # Only digits right after a word that names a code ("code is 482913", "PIN: 1234"), and never part of a date.
    ("CODE", re.compile(r"\b(?:code|passcode|OTP|PIN)\b(?:\s+(?:is|was))?\s*[:=#]?\s*(\d{3,4}[ -]\d{3,4}|\d{4,8})(?![\w/.-]?\d)", re.IGNORECASE)),
    # International (+44 20 7946 0958), North American ((555) 123-4567) or national with a trunk 0 (020 7946 0958);
    # PHONE_DIGITS keeps dates (05.12.2026) out.
    ("PHONE", re.compile(
        r"\+\d{1,3}(?:[ .-]?\(?\d{1,4}\)?){2,7}(?!\w)|(?<![\w+])(?:\(\d{3}\) ?|\d{3}[ .-]?)\d{3}[ .-]?\d{4}(?!\w)"
        r"|(?<![\w+.-])0\d{1,4}(?:[ .-]?\d{2,4}){2,4}(?![\w.-]?\d)"
    )),
]
PHONE_DIGITS = 9
WORD = r"[A-ZÀ-Þ](?:[^\W\d_]|['’-](?=[^\W\d_]))+"  # José, O'Brien
# Who a mail is to or from, by its greeting ("Hi Frank,") or sign-off ("Best regards,\nAna").
# A surname only when the greeting line ends right after it ("Hi Jane Doe,"), never the next sentence's first word.
GREETING = re.compile(rf"\b(?:Hi|Hello|Hey|Dear|Thanks|Thank you|Cheers)[ ,]+({WORD} {WORD}(?=[ \t]*[,!:\n])|{WORD})\b")
SIGN_OFF = re.compile(
    rf"\b(?:[Rr]egards|Thanks|Cheers|Best|Sincerely|Yours|Love)[,!.]?[ \t]*(?:\n[ \t]*){{1,2}}({WORD}(?: {WORD})?)[ \t]*$",
    re.MULTILINE,
)


class Redaction:
    """One per AI request: `names` are known people (the mail's sender and recipients), each also matched by its parts."""

    def __init__(self, names: Iterable[str]) -> None:
        self.names = {name.strip() for name in names if name and name.strip()}
        self.placeholders: dict[str, str] = {}  # real value -> placeholder
        self.values: dict[str, str] = {}  # placeholder -> real value
        self.taken: set[str] = set()  # placeholder-like text already in the mail: never issued, never restored
        self.issued: dict[str, int] = {}  # kind -> highest number issued

    def redact(self, text: str) -> str:
        self.taken |= set(PLACEHOLDER.findall(text))
        names = self.names | {found for pattern in (GREETING, SIGN_OFF) for found in pattern.findall(text)}
        for kind, pattern in PATTERNS:
            text = pattern.sub(lambda match: self.swap(match, kind), text)
        parts = {part for name in names for part in re.split(r"[\s,]+", name) if len(part) > 1 and part[0].isupper()}
        # Whole names before their parts, so "Ana Lopez" is one person rather than two.
        for name in sorted(names | parts, key=lambda name: (-len(name), name)):
            text = re.sub(rf"(?<![\w@]){re.escape(name)}(?!\w)", lambda match: self.swap(match, "PERSON"), text)
        return text

    def swap(self, match: re.Match[str], kind: str) -> str:
        if kind == "PHONE" and sum(character.isdigit() for character in match.group(0)) < PHONE_DIGITS:
            return match.group(0)
        group = 1 if match.re.groups else 0
        value = match.group(group)
        if value not in self.placeholders:
            number = self.issued.get(kind, 0) + 1
            while f"{kind}_{number}" in self.taken:
                number += 1
            self.issued[kind] = number
            self.placeholders[value] = f"{kind}_{number}"
            self.values[f"{kind}_{number}"] = value
        start, end = match.span(group)
        whole = match.group(0)
        return whole[: start - match.start()] + self.placeholders[value] + whole[end - match.start():]

    def restore(self, text: str) -> str:
        """Raises AIProposalError for a placeholder the AI made up: the owner must never see "Hi PERSON_9"."""

        def value(match: re.Match[str]) -> str:
            placeholder = match.group(0)
            if placeholder in self.taken:
                return placeholder  # it was in the mail itself
            if placeholder not in self.values:
                raise AIProposalError(f"the AI answered with an unknown placeholder {placeholder}")
            return self.restore(self.values[placeholder])  # a URL's value can hold the EMAIL_n issued before it

        return PLACEHOLDER.sub(value, text)

    def restore_model(self, model: ModelT) -> ModelT:
        """Every text in the AI's structured answer, restored; dates and numbers are left as they are."""

        def restored(value: object) -> object:
            if isinstance(value, str):
                return self.restore(value)
            if isinstance(value, list):
                return [restored(item) for item in value]
            if isinstance(value, dict):
                return {key: restored(item) for key, item in value.items()}
            return value

        return type(model).model_validate(restored(model.model_dump()))
