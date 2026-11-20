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
        text=("The deploy is done; please verify the dashboard.\n\n-- \nCara Jones | Site Reliability\n+1 555 0100 | cara@example.com\n"),
        kept=("The deploy is done; please verify the dashboard.",),
        removed=("Cara Jones", "+1 555 0100"),
    ),
    MinimizeCase(
        name="mobile footers",
        text=("Running 10 minutes late.\n\nSent from my iPhone\nGet Outlook for Android\n"),
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
        name="prose that only looks like history or a signature is kept",
        text=(
            "On Friday we ship the release\n"
            "please confirm, the vendor wrote:\n"
            "On the topic of the budget, the auditor wrote:\n"
            "> 50 units needed by Friday, >=5 boxes each\n"
            "Part 1 of the plan\n"
            "--\n"
            "Part 2: deadline Friday\n"
            "Sent from my warehouse on Monday: 40 pallets\n"
            "Flight details\n"
            "From: JFK\n"
            "Date: Nov 5\n"
            "Gate B12\n"
        ),
        kept=(
            "On Friday we ship the release",
            "the vendor wrote:",
            "On the topic of the budget, the auditor wrote:",
            "> 50 units needed by Friday, >=5 boxes each",
            "Part 2: deadline Friday",
            "Sent from my warehouse on Monday: 40 pallets",
            "From: JFK\nDate: Nov 5",
            "Gate B12",
        ),
        removed=(),
    ),
    MinimizeCase(
        name="outlook separator with a date line",
        subject="RE: Budget",
        text="Agreed.\n\n________________________________\nFrom: Bob <bob@example.com>\nDate: Mon, 2 Nov 2026\nSubject: Budget\n\nOld budget thread.\n",
        kept=("Agreed.",),
        removed=("From: Bob", "Old budget thread."),
    ),
    MinimizeCase(
        name="windows line endings",
        text="Sounds good.\r\n\r\nOn Mon, Nov 2, 2026, Ana <ana@example.com> wrote:\r\n> Lunch?\r\n\r\n-- \r\nAna Smith\r\n",
        kept=("Sounds good.",),
        removed=("wrote:", "Lunch?", "Ana Smith", "\r"),
    ),
    MinimizeCase(
        name="links keep their punctuation and untouched parameters",
        text=(
            "(see https://x.example/a?flag&id=a%20b&utm_source=news). Also https://x.example/b?utm_medium=mail, ok\n"
            "Unsubscribe: <https://x.example/u?id=7&utm_source=email>\n"
        ),
        kept=("(see https://x.example/a?flag&id=a%20b).", "https://x.example/b, ok", "<https://x.example/u?id=7>"),
        removed=("utm_source", "utm_medium"),
    ),
    MinimizeCase(
        name="forward after the forwarder's signature keeps the payload",
        subject="Fwd: Contract",
        text=(
            "FYI, needs your signature.\n"
            "-- \n"
            "Alice\n"
            "\n"
            "---------- Forwarded message ---------\n"
            "From: Legal <legal@example.com>\n"
            "Date: Mon, Nov 2, 2026\n"
            "Subject: Contract\n"
            "\n"
            "Please sign the contract by Friday.\n"
            "-- \n"
            "Legal Team, Example Corp\n"
        ),
        kept=("FYI, needs your signature.", "Forwarded message", "Please sign the contract by Friday."),
        removed=("Alice", "Legal Team, Example Corp"),
    ),
    MinimizeCase(
        name="outlook forward after the forwarder's signature keeps the payload",
        subject="FW: Invoice",
        text=(
            "See below.\n"
            "-- \n"
            "Alice\n"
            "\n"
            "________________________________\n"
            "From: Vendor <billing@vendor.example>\n"
            "Sent: Monday, November 2, 2026 8:00 AM\n"
            "Subject: Invoice\n"
            "\n"
            "Invoice 77 is due Nov 20.\n"
        ),
        kept=("See below.", "Invoice 77 is due Nov 20."),
        removed=("Alice",),
    ),
    MinimizeCase(
        name="attribution without an address",
        text="Count me in.\n\nOn Nov 1, 2026, Bob Smith wrote:\n> Dinner Saturday?\n",
        kept=("Count me in.",),
        removed=("wrote:", "Bob Smith", "Dinner Saturday?"),
    ),
    MinimizeCase(
        name="new content starting with On right before an attribution",
        text=("On Friday, please send the signed contract.\nOn Thu, Nov 1, 2026, Ana <ana@example.com> wrote:\n> Old request\n"),
        kept=("On Friday, please send the signed contract.",),
        removed=("wrote:", "Old request"),
    ),
    MinimizeCase(
        name="new content after a complete attribution line is kept",
        text=("On Thu, Nov 1, 2026, Ana <ana@example.com> wrote:\nPlease ask legal@example.com to review what I wrote:\n> Old request\n"),
        kept=("Please ask legal@example.com to review what I wrote:",),
        removed=("Old request",),  # the attribution itself may stay: it doesn't introduce the quote
    ),
    MinimizeCase(
        name="a fragment that looks like a query is the app's route, left alone",
        text="Open https://portal.example/#/settings?utm_source=email&tab=campaigns to update.\n",
        kept=("https://portal.example/#/settings?utm_source=email&tab=campaigns",),
        removed=(),
    ),
    MinimizeCase(
        name="an instruction shaped like an attribution is kept",
        text="On Friday, email support@example.com the text I wrote:\nPlease cancel my subscription.\n",
        kept=("On Friday, email support@example.com the text I wrote:", "Please cancel my subscription."),
        removed=(),
    ),
    MinimizeCase(
        name="quoted payload after a forward marker is the content",
        subject="Fwd: Invoice",
        text=("Please pay the forwarded invoice.\nBegin forwarded message:\n> Invoice 4471 is due Friday.\n"),
        kept=("Please pay the forwarded invoice.", "Invoice 4471 is due Friday."),
        removed=(),
    ),
    MinimizeCase(
        # What the IMAP plugin makes of an HTML forward: Begin forwarded message: + <blockquote>
        # <div>Invoice 4471 is due Friday.</div><div>-- </div><div>Ana Smith | +1 555 0100</div></blockquote>
        name="signature inside a quoted forwarded payload",
        subject="Fwd: Invoice",
        text=("Please pay this.\nBegin forwarded message:\n> Invoice 4471 is due Friday.\n> -- \n> Ana Smith | +1 555 0100\n"),
        kept=("Please pay this.", "Invoice 4471 is due Friday."),
        removed=("Ana Smith", "+1 555 0100"),
    ),
    MinimizeCase(
        name="a quoted signature run inside a payload ends where the quote depth changes",
        subject="Fwd: Invoice",
        text=(
            "Please pay this.\n"
            "---------- Forwarded message ---------\n"
            "> Invoice 4471 is due Friday.\n"
            "> > -- \n"
            "> > Ben Lee | Accounts\n"
            "> Wire it to the usual account.\n"
            "> -- \n"
            "> Ana Smith\n"
            "> ---------- Forwarded message ---------\n"
            "> Original invoice attached.\n"
        ),
        kept=("Invoice 4471 is due Friday.", "Wire it to the usual account.", "Forwarded message", "Original invoice attached."),
        removed=("Ben Lee", "Ana Smith"),
    ),
    MinimizeCase(
        name="an outlook-style forward after a quoted signature inside a payload is kept",
        subject="Fwd: Invoice",
        text=(
            "Begin forwarded message:\n"
            "> FYI\n"
            "> -- \n"
            "> Alice\n"
            "> -----Original Message-----\n"
            "> From: Billing <billing@example.com>\n"
            "> Sent: Monday\n"
            "> Invoice 4471 is due Friday.\n"
        ),
        kept=("FYI", "Original Message", "Invoice 4471 is due Friday."),
        removed=("Alice",),
    ),
    MinimizeCase(
        name="an answer after a quoted signature in a bottom-posted reply is kept",
        text=(
            "On Sun, Nov 1, 2026, Ben <ben@example.com> wrote:\n"
            "> Can you bring chairs?\n"
            "> -- \n"
            "> Ben Lee | +1 555 0199\n"
            "We can bring four chairs.\n"
        ),
        kept=("We can bring four chairs.",),
        removed=("Ben Lee", "Can you bring chairs?"),
    ),
    MinimizeCase(
        name="a forward marker inside quoted history keeps nothing extra",
        text=(
            "Paid, thanks.\nOn Mon, Nov 2, 2026, Ana <ana@example.com> wrote:\n> Begin forwarded message:\n> Invoice 4471 is due Friday.\n"
        ),
        kept=("Paid, thanks.",),
        removed=("Invoice 4471", "Begin forwarded message"),
    ),
    MinimizeCase(
        name="outlook headers inside an explicit forward are its payload",
        subject="Invoice",
        text=(
            "Please pay the forwarded invoice.\n"
            "Begin forwarded message:\n"
            "From: Vendor <vendor@example.com>\n"
            "Sent: Monday, November 2, 2026\n"
            "Invoice 4471 is due Friday.\n"
        ),
        kept=("Please pay the forwarded invoice.", "Invoice 4471 is due Friday."),
        removed=(),
    ),
    MinimizeCase(
        name="outlook reply history above a forward marker is still cut",
        subject="RE: Invoice",
        text=(
            "Done.\n"
            "________________________________\n"
            "From: Ana <ana@example.com>\n"
            "Sent: Monday, November 2, 2026\n"
            "Can you pay this?\n"
            "---------- Forwarded message ---------\n"
            "Invoice 4471 is due Friday.\n"
        ),
        kept=("Done.",),
        removed=("Can you pay this?", "Invoice 4471"),
    ),
    MinimizeCase(
        name="plain message is left alone",
        text="Hi Frank,\n\nCan you review the draft by Wednesday? https://docs.example/s?q=a%20b\n\nThanks,\nDana\n",
        kept=("Hi Frank,", "Can you review the draft by Wednesday?", "https://docs.example/s?q=a%20b", "Thanks,\nDana"),
        removed=(),
    ),
)
