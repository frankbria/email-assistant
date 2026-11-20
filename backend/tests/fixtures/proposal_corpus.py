"""Realistic inbox mail, one per kind of decision, for checking AI proposals against the real provider."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProposalCase:
    name: str
    sender: str
    subject: str
    body: str
    list_id: str | None = None


CORPUS = (
    ProposalCase(
        name="meeting request",
        sender="ana@example.com",
        subject="Q4 budget review",
        body="Hi Frank,\n\nCould we meet Thursday at 3pm to go over the Q4 budget? Let me know if another time works.\n\nThanks,\nAna",
    ),
    ProposalCase(
        name="invoice due",
        sender="billing@vendor.example",
        subject="Invoice 4471 due November 20",
        body="Your invoice 4471 for $240.00 is due on November 20, 2026. Pay online at https://vendor.example/pay/4471",
    ),
    ProposalCase(
        name="shipping notice",
        sender="noreply@shop.example",
        subject="Your order has shipped",
        body="Good news! Order 8812 has shipped and will arrive Wednesday. Track it at https://shop.example/track/8812",
    ),
    ProposalCase(
        name="newsletter",
        sender="news@weekly.example",
        subject="This week in product design",
        body="Five essays on onboarding flows, a talk on design systems, and our pick of the week's tools.",
        list_id="Weekly Design <weekly.example>",
    ),
    ProposalCase(
        name="contract for legal",
        sender="partner@acme.example",
        subject="Draft partnership agreement",
        body="Frank, attached is the draft partnership agreement. Can your legal team review the indemnity clause before Friday?",
    ),
    ProposalCase(
        name="check back later",
        sender="recruiter@talent.example",
        subject="Following up in December",
        body="Thanks for the chat. We're pausing hiring until December 1, 2026, and I'll reach out again then.",
    ),
    ProposalCase(
        name="security alert",
        sender="security@bank.example",
        subject="Update your account password",
        body="We noticed your password is over a year old. Please update it at https://bank.example/security before December 15.",
    ),
    ProposalCase(
        name="promotion",
        sender="deals@shop.example",
        subject="30% off running shoes this week",
        body="This week only: 30% off all running shoes. Unsubscribe at https://shop.example/unsubscribe",
        list_id="<deals.shop.example>",
    ),
)

# A club notice the AI would likely file away unprompted; the owner replied to the last one (#82).
RIDE_NOTICE = "Saturday long run is {miles} miles from the boathouse at 7am. Route map and water stops are on the club page."
EARLIER_RIDE = ProposalCase(
    name="earlier ride notice",
    sender="coach@runclub.example",
    subject="Saturday long run: 18 miles",
    body=RIDE_NOTICE.format(miles=18),
)
NEXT_RIDE = ProposalCase(
    name="next ride notice",
    sender="coach@runclub.example",
    subject="Saturday long run: 16 miles",
    body=RIDE_NOTICE.format(miles=16),
)
