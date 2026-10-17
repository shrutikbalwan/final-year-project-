"""Generate a password hash for HELMET_BOOTSTRAP_USERS; never writes credentials."""
from getpass import getpass

from backend.app.auth import hash_password


def main() -> None:
    password = getpass("New local API password (input hidden): ")
    confirm = getpass("Repeat password: ")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters.")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    print(hash_password(password))


if __name__ == "__main__":
    main()
