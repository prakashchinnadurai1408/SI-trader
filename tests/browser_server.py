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
from nifty100_weekly.nifty100_adapter.llm_connections import ProviderTimeout

if __name__ == "__main__":
    root = Path(os.environ["SI_TRADER_LLM_HOME"])
    root.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([{"symbol": "TEST", "close": 100., "daily_turnover_crore": 100.}])
    patch("nifty100_weekly.nifty100_adapter.web_workspace.load_nifty100", return_value=(frame, {"source": "Browser test fixture", "asOf": "2026-11-25"})).start()
    weekly_frame = pd.DataFrame([dict(symbol=f"TEST{i:03}", company_name=f"Fixture {i}", isin=f"FIXTURE{i}", close=100.+i,
        daily_turnover_crore=100., price_momentum_daily=-1., price_momentum_weekly=-5.+i/10) for i in range(100)])
    patch("nifty100_weekly.nifty100_adapter.web_app.load_nifty100", return_value=(weekly_frame, {"source":"Browser test fixture","asOf":"2026-11-25","covered":100,"universeSize":100,"unverifiedChecks":[]})).start()
    patch("nifty100_weekly.nifty100_adapter.evidence_hunter.load_nifty100", return_value=(weekly_frame, {"source":"Browser test fixture","asOf":"2026-11-25","covered":100,"universeSize":100,"unverifiedChecks":[]})).start()
    patch("nifty100_weekly.nifty100_adapter.evidence_hunter.download", return_value=b"<html>Primary source candidate</html>").start()
    patch("nifty100_weekly.nifty100_adapter.evidence_hunter.agent", return_value={"priority":["promoter_pledging_pct","debt_equity_ratio"]}).start()
    patch("nifty100_weekly.nifty100_adapter.web_app.installed_models", return_value=["fixture"]).start()
    patch("nifty100_weekly.nifty100_adapter.full_catalogue.pe_data", return_value={}).start()
    patch("nifty100_weekly.nifty100_adapter.full_catalogue.ownership_data", return_value={}).start()
    patch("nifty100_weekly.nifty100_adapter.full_catalogue.collect_public_records", return_value=({},[])).start()
    patch("nifty100_weekly.nifty100_adapter.web_app.generate_plan", side_effect=[ProviderTimeout("The AI provider timed out. Test/select another model in LLM Configuration."), {"basket":[{"symbol":"TEST099","price":199.,"weight":20,"rationale":"Fixture"}],"title":"Fixture","thesis":"Fixture"}]).start()
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
