from __future__ import annotations

import smtplib
import socket
import ssl

from app.services.delivery.base import DeliveryChannel, DeliveryError, OutgoingEmail, build_mime


class SMTPChannel(DeliveryChannel):
    name = "smtp"

    def _connect(self, c: dict):
        host, port, sec = c["host"], int(c.get("port", 587)), c.get("security", "starttls")
        ctx = ssl.create_default_context()
        try:
            if sec == "ssl":
                s = smtplib.SMTP_SSL(host, port, context=ctx, timeout=20)
            else:
                s = smtplib.SMTP(host, port, timeout=20)
                s.ehlo()
                if sec == "starttls":
                    s.starttls(context=ctx)
                    s.ehlo()
            s.login(c["username"], c["password"])
            return s
        except smtplib.SMTPAuthenticationError as exc:
            raise DeliveryError("SMTP authentication failed. Check the username and app password.", needs_reauth=True) from exc
        except (smtplib.SMTPException, OSError, socket.timeout) as exc:
            raise DeliveryError(f"Could not connect to the SMTP server ({type(exc).__name__}).", retryable=True) from exc

    def verify(self, credentials: dict) -> None:
        self._connect(credentials).quit()

    def send(self, credentials: dict, message: OutgoingEmail) -> str | None:
        s = self._connect(credentials)
        try:
            mime = build_mime(message)
            s.send_message(mime)
            return mime["Message-ID"]
        except smtplib.SMTPRecipientsRefused as exc:
            raise DeliveryError("The recipient address was refused by the mail server.") from exc
        except smtplib.SMTPException as exc:
            raise DeliveryError(f"SMTP error: {type(exc).__name__}", retryable=True) from exc
        finally:
            try:
                s.quit()
            except Exception:  # noqa: BLE001
                pass
