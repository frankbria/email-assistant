"""Gmail plugin entry point (stdio; the app starts it): python -m gmail_plugin.server"""

from imap_mailbox.server import build_server
from gmail_plugin.mailbox import GmailMailbox
from gmail_plugin.settings import GmailSettings


def main() -> None:
    settings = GmailSettings()  # type: ignore[call-arg]  # required fields come from the environment
    build_server(GmailMailbox(settings), name="gmail").run()


if __name__ == "__main__":
    main()
