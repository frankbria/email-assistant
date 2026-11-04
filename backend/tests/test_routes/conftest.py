from collections.abc import AsyncIterator, Iterator

import pytest

from app.api.routers.jobs import plugin_registry
from app.main import app
from app.plugins.registry import PluginRegistry
from app.services.ai_provider import get_ai_provider
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import connected
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import Mailbox


@pytest.fixture
async def plugins(mailbox: Mailbox) -> AsyncIterator[PluginRegistry]:
    """The reference IMAP plugin on the owner's GreenMail account, serving the API's mailbox actions."""
    mailbox.create_folder("Archive")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        app.dependency_overrides[plugin_registry] = lambda: registry
        yield registry
    app.dependency_overrides.pop(plugin_registry, None)


@pytest.fixture
def ai() -> Iterator[FakeAIProvider]:
    provider = FakeAIProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_ai_provider)
