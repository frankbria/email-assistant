"""Mail bodies as plugins deliver them (`MessageDetail.text`), with what minimizing must keep and drop.
Reused wherever the AI request is checked for minimized content only (spec AC-R.2)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MinimizeCase:
    name: str
    text: str
    kept: tuple[str, ...]
    removed: tuple[str, ...]
    subject: str = ""


CORPUS = (
    MinimizeCase(
        name="gmail top-posted reply",
        text=(
            "Thursday at 3 works for me. Can you send the agenda?\n"
            "\n"
            "On Mon, Nov 2, 2026 at 10:04 AM Ana Smith <ana@example.com> wrote:\n"
            "> Could we meet this week to go over the Q4 budget?\n"
            "> Ana\n"
        ),
        kept=("Thursday at 3 works for me. Can you send the agenda?",),
        removed=("wrote:", "Q4 budget", "> Ana"),
    ),
    MinimizeCase(
        name="attribution wrapped over two lines",
        text=(
            "Approved.\n"
            "\n"
            "On Mon, Nov 2, 2026 at 10:04 AM Ana Smith via Billing <\n"
            "billing@example.com> wrote:\n"
            "> Please approve invoice 4471.\n"
        ),
        kept=("Approved.",),
        removed=("wrote:", "billing@example.com", "invoice 4471"),
    ),
    MinimizeCase(
        name="bottom-posted inline answers",
        text=(
            "On Sun, Nov 1, 2026, Ben <ben@example.com> wrote:\n"
            "> Are you coming on Saturday?\n"
            "Yes, both of us.\n"
            "> Can you bring chairs?\n"
            "We can bring four chairs.\n"
        ),
        kept=("Yes, both of us.", "We can bring four chairs."),
        removed=("wrote:", "Are you coming on Saturday?", "Can you bring chairs?"),
    ),
    MinimizeCase(
        name="outlook original message",
        text=(
            "Please see the contract below and sign by Friday.\n"
            "\n"
            "-----Original Message-----\n"
            "From: Legal <legal@example.com>\n"
            "Sent: Monday, November 2, 2026 9:00 AM\n"
            "Subject: Contract v3\n"
            "Earlier thread about indemnity clauses.\n"
        ),
        kept=("Please see the contract below and sign by Friday.",),
        removed=("Original Message", "Sent: Monday", "indemnity clauses"),
    ),
    MinimizeCase(
        name="original message without a sent line",
        text=(
            "Yes, ship it.\n"
            "\n"
            "-----Original Message-----\n"
            "From: Dev <dev@example.com>\n"
            "Date: Mon, 2 Nov 2026 09:00:00 -0800\n"
            "Can we ship release 4.2 today?\n"
        ),
        kept=("Yes, ship it.",),
        removed=("Original Message", "release 4.2"),
    ),
    MinimizeCase(
        name="outlook reply header block",
        subject="RE: Your plan renews soon",
        text=(
            "Let's cancel it.\n"
            "\n"
            "________________________________\n"
            "From: Vendor Billing <billing@vendor.example>\n"
            "Sent: Sunday, November 1, 2026 4:12 PM\n"
            "To: Frank <frank@example.com>\n"
            "Subject: Your plan renews soon\n"
            "\n"
            "Old renewal notice text.\n"
        ),
        kept=("Let's cancel it.",),
        removed=("From: Vendor Billing", "Sent: Sunday", "Old renewal notice text.", "________________"),
    ),
    MinimizeCase(
        name="outlook forward keeps what was forwarded",
        subject="FW: Your plan renews soon",
        text=(
            "Renew or cancel?\n"
            "\n"
            "________________________________\n"
            "From: Vendor Billing <billing@vendor.example>\n"
            "Sent: Sunday, November 1, 2026 4:12 PM\n"
            "Subject: Your plan renews soon\n"
            "\n"
            "Your plan renews on Nov 15 for $240.\n"
        ),
        kept=("Renew or cancel?", "Your plan renews on Nov 15 for $240."),
        removed=(),
    ),
    MinimizeCase(
        name="gmail forward keeps what was forwarded",
        subject="Fwd: Flight change",
        text=(
            "FYI, can you rebook?\n"
            "\n"
            "---------- Forwarded message ---------\n"
            "From: Airline <noreply@airline.example>\n"
            "Date: Sun, Nov 1, 2026 at 8:00 PM\n"
            "Subject: Flight change\n"
            "\n"
            "Flight 212 now departs at 6:40 AM.\n"
        ),
        kept=("FYI, can you rebook?", "Flight 212 now departs at 6:40 AM."),
        removed=(),
    ),
    MinimizeCase(
        name="delimited signature",
        text=(
            "The deploy is done; please verify the dashboard.\n"
            "\n"
            "-- \n"
            "Cara Jones | Site Reliability\n"
            "+1 555 0100 | cara@example.com\n"
        ),
        kept=("The deploy is done; please verify the dashboard.",),
        removed=("Cara Jones", "+1 555 0100"),
    ),
    MinimizeCase(
        name="mobile footers",
        text=(
            "Running 10 minutes late.\n"
            "\n"
            "Sent from my iPhone\n"
            "Get Outlook for Android\n"
        ),
        kept=("Running 10 minutes late.",),
        removed=("Sent from my iPhone", "Get Outlook for Android"),
    ),
    MinimizeCase(
        name="tracking parameters",
        text=(
            "Your order shipped: https://shop.example/track?order=8812&utm_source=email&utm_medium=mail&fbclid=abc123\n"
            "Review it: https://shop.example/review?gclid=XYZ&mc_eid=99\n"
        ),
        kept=("https://shop.example/track?order=8812", "https://shop.example/review"),
        removed=("utm_source", "utm_medium", "fbclid", "gclid", "mc_eid"),
    ),
    MinimizeCase(
        name="plain message is left alone",
        text="Hi Frank,\n\nCan you review the draft by Wednesday? https://docs.example/s?q=a%20b\n\nThanks,\nDana\n",
        kept=("Hi Frank,", "Can you review the draft by Wednesday?", "https://docs.example/s?q=a%20b", "Thanks,\nDana"),
        removed=(),
    ),
)
