"""Forwarding-based ingestion (issue #29) and the legacy classifier pipeline it fed
(issue #146) are removed; the job pipeline replaces them (spec §8)."""

import pytest

from app.main import app

REMOVED_PATHS = [
    "/api/v1/email/incoming",
    "/api/v1/email/new-email",
    "/api/v1/email/get/{address}",
    "/api/v1/admin/webhook/security",
    "/api/v1/email/",
    "/api/v1/email/spam",
    "/api/v1/email/{email_id}/not-spam",
    "/api/v1/email/{email_id}/archive",
    "/api/v1/settings/email",
]


@pytest.mark.parametrize("path", REMOVED_PATHS)
def test_forwarding_route_is_not_registered(path):
    assert path not in app.openapi()["paths"]


@pytest.mark.parametrize(
    "module",
    [
        "mailslurp_client",
        "slowapi",
        "app.services.mailbox_provisioning",
        "app.services.onboarding",
        "app.services.webhook_security",
        "app.models.webhook_security",
        "app.utils.email_retrieval_utils",
        "app.api.routers.admin",
        "app.api.routers.email",
        "app.services.action_suggester",
        "app.services.ai_client",
        "app.services.context_classifier",
        "app.services.task_classifier",
        "app.services.email_task_mapper",
        "app.services.duplicate_detection",
        "app.services.email_summarizer",
        "app.strategies",
        "app.utils.email_utils",
        "app.models.assistant_task",
        "app.models.email_message",
    ],
)
def test_forwarding_module_is_gone(module):
    with pytest.raises(ModuleNotFoundError):
        __import__(module)
