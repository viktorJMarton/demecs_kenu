#!/usr/bin/env python3
"""Send one test email through the SMTP server configured in .env."""

from __future__ import annotations

import os
import smtplib
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv


# A tesztlevél erre a címre érkezik. Szükség esetén ezt az értéket írd át.
TEST_RECIPIENT = "martonviktor666@gmail.com"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Hiányzó környezeti változó: {name}")
    return value


def send_test_email() -> None:
    smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    smtp_username = required_env("EMAIL_SMTP_USERNAME")
    smtp_password = required_env("EMAIL_SMTP_PASSWORD")
    sender = os.getenv("EMAIL_FROM", smtp_username).strip() or smtp_username
    use_tls = os.getenv("EMAIL_SMTP_USE_TLS", "true").lower() != "false"

    sent_at = datetime.now(timezone.utc).astimezone()
    message = EmailMessage()
    message["Subject"] = "SMTP tesztlevél"
    message["From"] = sender
    message["To"] = TEST_RECIPIENT
    message.set_content(
        "Ez egy automatikus tesztlevél a kajak-kenu szerverről.\n\n"
        f"Küldés időpontja: {sent_at:%Y-%m-%d %H:%M:%S %z}\n"
        "Ha ezt az üzenetet megkaptad, az SMTP-beállítás működik.\n"
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


def main() -> int:
    try:
        send_test_email()
    except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
        print(f"A tesztlevél küldése sikertelen: {exc}", file=sys.stderr)
        return 1

    print(f"A tesztlevél elküldve: {TEST_RECIPIENT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
