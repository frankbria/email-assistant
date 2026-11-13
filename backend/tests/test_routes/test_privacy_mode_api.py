# Redacted-cloud privacy mode (spec §8.2, AC-R.1): a real message in GreenMail goes through the real pipeline; the
# AI request the FakeAIProvider captures holds none of its personal details, and the owner's job shows the real ones.
import re

import pytest

from app.models.user_settings import UserSettings
from app.pipeline.proposal import Proposal
from tests.test_pipeline.test_run import run_pass
from tests.test_sync.test_inbox_sync import add_owner
from tests.utils.auth import OWNER_ID
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import Mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
SENDER = "ana.lopez@acme.example"
PHONE = "(555) 123-4567"
URL = "https://billing.acme.example/inv/42"
BODY = f"""Hi Frank,

The March invoice is ready. Please pay it at {URL} by Friday.
Questions? Call me on {PHONE} or write to {SENDER}.

Best regards,
Ana"""
# The AI only ever sees placeholders, so that is all it can answer with.
ANSWER = Proposal(
    needs_owner=False,
    verb="todo",
    title="Pay PERSON_1's March invoice for PERSON_2",
    evidence=["Call me on PHONE_1"],
    link="URL_1",
    confidence=0.9,
)


async def test_ac_r1_the_ai_request_holds_no_personal_details_and_the_owners_job_holds_the_real_ones(
    test_db, async_client, mailbox: Mailbox
):
    await add_owner(test_db, OWNER_ID)
    await UserSettings(user_id=OWNER_ID, privacy_mode="redacted_cloud").insert()
    mailbox.deliver(sender=f"Ana Lopez <{SENDER}>", subject="Invoice from Ana Lopez", body=BODY)
    ai = FakeAIProvider(result=ANSWER)

    await run_pass(test_db, mailbox, ai)

    [prompt] = ai.prompts
    for real in (SENDER, PHONE, URL, "Ana", "Lopez", "Frank"):
        assert real not in prompt, real
    assert not re.search(r"[\w.+-]+@[\w-]+\.\w+|https?://", prompt)
    assert {"PERSON_1", "PERSON_2", "EMAIL_1", "PHONE_1", "URL_1"} <= set(re.findall(r"[A-Z]+_\d+", prompt))
    [card] = (await async_client.get("/api/v1/jobs")).json()
    job = card["job"]
    assert (job["ask_owner"], job["title"]) == (False, "Pay Ana Lopez's March invoice for Frank")
    assert job["evidence"] == [f"Call me on {PHONE}"] and job["artifacts"]["link"] == URL


async def test_in_full_cloud_mode_the_default_the_ai_sees_the_mail_as_it_is(test_db, mailbox: Mailbox):
    await add_owner(test_db, OWNER_ID)
    mailbox.deliver(sender=f"Ana Lopez <{SENDER}>", subject="Invoice from Ana Lopez", body=BODY)
    ai = FakeAIProvider(result=ANSWER)

    await run_pass(test_db, mailbox, ai)

    [prompt] = ai.prompts
    assert all(real in prompt for real in (SENDER, PHONE, URL, "Frank")) and "PERSON_1" not in prompt


async def test_a_name_mentioned_only_mid_sentence_never_reaches_the_ai_and_comes_back_in_the_job(test_db, async_client, mailbox: Mailbox):
    await add_owner(test_db, OWNER_ID)
    await UserSettings(user_id=OWNER_ID, privacy_mode="redacted_cloud").insert()
    body = BODY.replace("Questions?", "If the late fee looks wrong, ask Maria about it first.")
    mailbox.deliver(sender=f"Ana Lopez <{SENDER}>", subject="Invoice from Ana Lopez", body=body)
    # Whole names before parts, then by name: Ana Lopez, Frank, Maria.
    ai = FakeAIProvider(result=ANSWER.model_copy(update={"title": "Ask PERSON_3 about the late fee"}))

    await run_pass(test_db, mailbox, ai)

    [prompt] = ai.prompts
    assert "Maria" not in prompt and "ask PERSON_3 about it" in prompt
    [card] = (await async_client.get("/api/v1/jobs")).json()
    assert card["job"]["title"] == "Ask Maria about the late fee"
