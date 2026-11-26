"""Disposable local + HTTPS-hosted servers for browser regression tests only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import ssl
from threading import Event, Thread
from unittest.mock import patch
import pandas as pd

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from nifty100_weekly.nifty100_adapter.deployment import Runtime, password_hash
from nifty100_weekly.nifty100_adapter.web_app import create_server

if __name__ == "__main__":
    root = Path(os.environ["SI_TRADER_LLM_HOME"])
    root.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([{"symbol": "TEST", "close": 100., "daily_turnover_crore": 100.}])
    patch("nifty100_weekly.nifty100_adapter.web_workspace.load_nifty100", return_value=(frame, {"source": "Browser test fixture", "asOf": "2026-11-25"})).start()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256()))
    (root / "test-key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (root / "test-cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    local = create_server(port=0, runtime=Runtime())
    hosted = create_server(port=0, runtime=Runtime(True, "", "operator@example.com", password_hash("FixturePassword123!")))
    hosted.runtime = replace(hosted.runtime, origin=f"https://127.0.0.1:{hosted.server_port}")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(root / "test-cert.pem", root / "test-key.pem")
    hosted.socket = context.wrap_socket(hosted.socket, server_side=True)
    for server in (local, hosted):
        Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({"local": f"http://127.0.0.1:{local.server_port}", "hosted": hosted.runtime.origin}), flush=True)
    Event().wait()
