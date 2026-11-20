"""Seeds and inspects the Playwright suite's stack (frontend/playwright.config.ts), from backend/:

    uv run python -m tests.e2e.seed_job reset
    uv run python -m tests.e2e.seed_job job reply --draft "Thursday works."   # prints the job as JSON
    uv run python -m tests.e2e.seed_job job reply --ask-owner "the AI gave no usable proposal"
    uv run python -m tests.e2e.seed_job job archive_noise --noise-rationale "A promotional mailing"
    uv run python -m tests.e2e.seed_job inbox <address>                       # prints its mail as JSON

A job is seeded the way test_jobs_api.job_from makes one: a sender really mails the owner's GreenMail
mailbox (E2E_MAILBOX_ACCOUNT, the one the backend's plugin reads), then the matching Message and Job
are stored for the owner who signed up in the browser.
"""

import argparse
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pymongo import AsyncMongoClient

from app.config import get_settings
from app.main import init_db
from app.models.job import Artifacts, Job
from app.models.message import Message
from app.plugins.config import load_plugins_config
from tests.utils.mail_server import Mailbox, new_mailbox, wait_until_ready

QUESTION = "Could we meet Thursday at 3pm?"


async def connect() -> AsyncMongoClient[dict[str, object]]:
    settings = get_settings()
    if "_test" not in settings.current_mongodb_db:
        raise SystemExit(f"refusing to touch {settings.current_mongodb_db}: the E2E database name must contain _test")
    return await init_db(settings)


async def reset() -> None:
    """Every collection emptied, Better Auth's included, so the suite signs up a fresh owner."""
    client = await connect()
    database = client[get_settings().current_mongodb_db]
    for name in await database.list_collection_names():
        await database[name].delete_many({})
    await client.close()


async def seed_job(
    verb: str, draft: str | None, forward_to: str | None, ask_owner: str | None, noise_rationale: str | None
) -> dict[str, str]:
    """`ask_owner`: the problem that sends the job to the owner, with `verb` as its one suggestion, as ask_owner_job makes it."""
    client = await connect()
    owner = await client[get_settings().current_mongodb_db]["user"].find_one({}, {"_id": 1})
    if owner is None:
        raise SystemExit("no owner yet: sign up in the browser first")
    [plugin] = load_plugins_config(Path(os.environ["PLUGINS_CONFIG"]))
    wait_until_ready()
    mailbox = Mailbox(os.environ["E2E_MAILBOX_ACCOUNT"])
    for folder in ("Archive", "Sent"):  # where approving archives the mail and files the sent copy
        mailbox.create_folder(folder)
    sender = new_mailbox()
    title = f"Ana asks to meet Thursday ({uuid.uuid4().hex[:8]})"  # tests run in parallel against one queue
    ref = sender.deliver_to(mailbox, subject=title, body=QUESTION)
    message = Message.model_validate(
        {
            "owner_id": str(owner["_id"]),
            "plugin_id": plugin.id,
            "ref": ref,
            "message_id": ref,
            "sender": {"name": "Ana", "email": sender.address},
            "to": [{"email": mailbox.address}],
            "cc": [],
            "date": datetime.now(UTC),
            "subject": title,
            "snippet": "",
            "pipeline_done": True,
        }
    )
    await message.insert()
    assert message.id is not None
    job = Job(
        owner_id=str(owner["_id"]),
        verb=verb,
        title=title,
        evidence=[QUESTION],
        artifacts=Artifacts(draft=draft, forward_to=forward_to, noise_rationale=noise_rationale),
        message_ids=[message.id],
        ask_owner=ask_owner is not None,
        suggested_verbs=[verb] if ask_owner else [],
        problems=[ask_owner] if ask_owner else [],
    )
    await job.insert()
    await client.close()
    return {"id": str(job.id), "title": title, "sender": sender.address}


def inbox(address: str) -> list[dict[str, str]]:
    return [{"subject": str(mail["Subject"]), "body": mail.get_content()} for mail in Mailbox(address).messages("INBOX")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("reset")
    job = commands.add_parser("job")
    job.add_argument("verb", choices=["reply", "forward", "archive_noise"])
    job.add_argument("--draft")
    job.add_argument("--forward-to")
    job.add_argument("--ask-owner", metavar="PROBLEM")
    job.add_argument("--noise-rationale")
    commands.add_parser("inbox").add_argument("address")
    arguments = parser.parse_args()
    if arguments.command == "reset":
        asyncio.run(reset())
    elif arguments.command == "job":
        print(
            json.dumps(
                asyncio.run(seed_job(arguments.verb, arguments.draft, arguments.forward_to, arguments.ask_owner, arguments.noise_rationale))
            )
        )
    else:
        print(json.dumps(inbox(arguments.address)))


if __name__ == "__main__":
    main()
