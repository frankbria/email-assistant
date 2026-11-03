# backend/tests/utils/tls_relay.py
"""A stand-in for Proton Bridge's TLS: a generated certificate valid for 127.0.0.1 and an
implicit-TLS front-end relaying plaintext to the GreenMail test server."""

import datetime
import functools
import ipaddress
import select
import socket
import ssl
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID

from tests.utils.mail_server import IMAP_PORT, SMTP_PORT


def write_certificate(directory: Path, name: str) -> tuple[Path, Path]:
    key = Ed25519PrivateKey.generate()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, None)  # Ed25519 signs without a separate hash
    )
    cert_path, key_path = directory / f"{name}.pem", directory / f"{name}.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_path, key_path


def start_tls_relay(target_port: int, cert_path: Path, key_path: Path, listen_port: int = 0) -> int:
    """Implicit-TLS front-end on a random port, forwarding plaintext to target_port."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    listener = socket.create_server(("127.0.0.1", listen_port))

    def relay(secure: ssl.SSLSocket, upstream: socket.socket) -> None:
        # One thread per connection: an SSLSocket must not be read and written from two threads at
        # once (OpenSSL state isn't thread-safe), which garbled replies now and then under load.
        try:
            while True:
                readable = [secure] if secure.pending() else select.select([secure, upstream], [], [])[0]
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is secure else secure).sendall(data)
        except OSError:  # ssl.SSLError is an OSError
            pass
        finally:
            for end in (secure, upstream):
                end.close()

    def handle(client: socket.socket) -> None:
        try:
            secure = context.wrap_socket(client, server_side=True)
        except (ssl.SSLError, OSError):
            client.close()
            return
        relay(secure, socket.create_connection(("127.0.0.1", target_port)))

    def serve() -> None:
        while True:
            client, _ = listener.accept()
            threading.Thread(target=handle, args=(client,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    return listener.getsockname()[1]


@dataclass(frozen=True)
class FakeBridge:
    cert: Path
    wrong_cert: Path
    imap_port: int
    smtp_port: int


@functools.cache
def fake_bridge() -> FakeBridge:
    """One TLS front-end per test session (IMAP and SMTP), plus a certificate that doesn't match."""
    directory = Path(tempfile.mkdtemp(prefix="fake-bridge-"))
    cert_path, key_path = write_certificate(directory, "bridge")
    wrong_cert_path, _ = write_certificate(directory, "some-other-bridge")
    return FakeBridge(
        cert=cert_path,
        wrong_cert=wrong_cert_path,
        imap_port=start_tls_relay(IMAP_PORT, cert_path, key_path),
        smtp_port=start_tls_relay(SMTP_PORT, cert_path, key_path),
    )
