"""Gmail plugin entry point (stdio; the app starts it): python -m gmail_plugin.server"""

from mcp.types import CallToolResult

from imap_mailbox.server import build_server, respond
from gmail_plugin.mailbox import GmailMailbox
from gmail_plugin.settings import GmailSettings


def main() -> None:
    settings = GmailSettings()  # type: ignore[call-arg]  # required fields come from the environment
    mailbox = GmailMailbox(settings)
    server = build_server(mailbox, name="gmail")

    @server.tool()
    def setup_warnings() -> CallToolResult:
        """Setup problems that don't stop mail (Gmail's Auto-Expunge setting). Run on the owner's
        setup check only: it adds a probe message to the Trash."""
        return respond(mailbox.setup_warnings)

    server.run()


if __name__ == "__main__":
    main()
