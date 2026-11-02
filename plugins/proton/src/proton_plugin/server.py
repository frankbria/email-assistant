"""Proton plugin entry point: stdio by default, `http` for Streamable HTTP on the tailnet."""

import hmac
import sys

import uvicorn
from starlette.types import ASGIApp, Receive, Scope, Send

from imap_mailbox.server import build_server
from proton_plugin.mailbox import ProtonMailbox
from proton_plugin.settings import load_settings


class BearerTokenGuard:
    """Rejects HTTP requests that don't carry `Authorization: Bearer <token>`."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            supplied = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self.expected):
                await send({"type": "http.response.start", "status": 401, "headers": [(b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
        await self.app(scope, receive, send)


def main() -> None:
    settings = load_settings()
    server = build_server(ProtonMailbox(settings), name="proton")
    if sys.argv[1:2] != ["http"]:
        server.run()
        return
    if not settings.http_host or not settings.http_token:
        raise SystemExit("HTTP mode needs MAILBOX_HTTP_HOST (this machine's Tailscale IP) and MAILBOX_HTTP_TOKEN.")
    app = BearerTokenGuard(server.streamable_http_app(host=settings.http_host), settings.http_token)
    uvicorn.run(app, host=settings.http_host, port=settings.http_port)


if __name__ == "__main__":
    main()
