"""Forwarding-based ingestion is removed (spec §3 non-goals, §12; issue #29)."""

import pytest

from app.main import app

REMOVED_PATHS = [
    "/api/v1/email/incoming",
    "/api/v1/email/new-email",
    "/api/v1/email/get/{address}",
    "/api/v1/admin/webhook/security",
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
    ],
)
def test_forwarding_module_is_gone(module):
    with pytest.raises(ModuleNotFoundError):
        __import__(module)
