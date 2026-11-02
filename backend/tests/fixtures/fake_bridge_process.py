"""A stand-in for the Proton Bridge *process*: implicit-TLS front-ends relaying to the
auth-enabled GreenMail, until killed. Usage: fake_bridge_process.py CERT KEY IMAP_PORT SMTP_PORT PID_FILE"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.utils.tls_relay import start_tls_relay  # noqa: E402

cert, key, imap_port, smtp_port, pid_file = sys.argv[1:6]
start_tls_relay(int(os.environ.get("MAIL_AUTH_TEST_IMAP_PORT", "3144")), Path(cert), Path(key), listen_port=int(imap_port))
start_tls_relay(int(os.environ.get("MAIL_AUTH_TEST_SMTP_PORT", "3026")), Path(cert), Path(key), listen_port=int(smtp_port))
Path(pid_file).write_text(str(os.getpid()))
while True:
    time.sleep(60)
