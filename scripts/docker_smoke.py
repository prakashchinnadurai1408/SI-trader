"""Exercise the built Linux image with disposable credentials and storage."""
import json
import http.client
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
from nifty100_weekly.nifty100_adapter.deployment import password_hash

name = "si-ci-" + uuid4().hex[:12]
with tempfile.TemporaryDirectory() as folder:
    file = Path(folder) / "container.env"
    file.write_text("\n".join([
        "SI_TRADER_PUBLIC_ORIGIN=https://trader.example", "SI_TRADER_AUTH_USER=operator@example.com",
        "SI_TRADER_AUTH_PASSWORD_HASH=" + password_hash("FixturePassword123!"),
        "SI_TRADER_ENCRYPTION_KEY=" + Fernet.generate_key().decode(),
    ]), encoding="utf-8")
    file.chmod(0o600)
    try:
        subprocess.run(["docker", "run", "-d", "--name", name, "--env-file", str(file), "--read-only",
                        "--tmpfs", "/tmp", "--tmpfs", "/data:uid=10001,gid=10001", "-p", "127.0.0.1::8080", "si-trader-ci"], check=True, stdout=subprocess.DEVNULL)
        port = subprocess.check_output(["docker", "port", name, "8080"], text=True).strip().rsplit(":", 1)[1]
        base = "http://127.0.0.1:" + port
        # Health probes deliberately use a loopback Host for the private container port.
        for attempt in range(30):
            try:
                with urlopen(Request(base + "/healthz", headers={"Host": "127.0.0.1:8080"}), timeout=2) as response:
                    assert json.load(response)["status"] == "ok"
                break
            except (URLError, OSError, http.client.HTTPException):
                if attempt == 29:
                    subprocess.run(["docker", "logs", "--tail", "40", name], check=False)
                    raise
                time.sleep(0.5)
        request = Request(base + "/api/broker", data=b"{}", headers={"Host": "trader.example", "Origin": "https://trader.example", "Content-Type": "application/json"})
        try:
            urlopen(request, timeout=5)
            raise AssertionError("Unauthenticated broker endpoint accepted")
        except HTTPError as error:
            assert error.code == 401
        print("Docker health and authentication boundary: PASS")
    finally:
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
