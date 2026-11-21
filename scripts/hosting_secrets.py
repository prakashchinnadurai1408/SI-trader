"""Create a private environment file interactively; never print generated secrets."""
import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
from nifty100_weekly.nifty100_adapter.deployment import password_hash


def main():
    target = Path(input("Private environment file path (outside the repository): ")).expanduser().resolve()
    root = Path(__file__).resolve().parents[1]
    if target.is_relative_to(root):
        raise SystemExit("Choose a path outside the repository.")
    email = input("Operator email: ").strip()
    origin = input("HTTPS origin, without trailing slash: ").strip()
    password = getpass.getpass("Operator password (12+ characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords differ.")
    if any(c in email + origin for c in "\r\n'\"") or "@" not in email or not origin.startswith("https://"):
        raise SystemExit("Enter a valid email and HTTPS origin.")
    content = {"SI_TRADER_MODE": "hosted", "SI_TRADER_PUBLIC_ORIGIN": origin, "SI_TRADER_AUTH_USER": email,
               "SI_TRADER_AUTH_PASSWORD_HASH": password_hash(password), "SI_TRADER_ENCRYPTION_KEY": Fernet.generate_key().decode(),
               "SI_TRADER_DATA_DIR": "/data"}
    # Exclusive creation prevents accidental encryption-key replacement.
    with target.open("x", encoding="utf-8") as file:
        target.chmod(0o600)
        file.write("\n".join(f"{key}='{value}'" for key, value in content.items()) + "\n")
    print("Private environment file created. Restrict Windows file access to your user; retain a secure backup.")


if __name__ == "__main__":
    main()
