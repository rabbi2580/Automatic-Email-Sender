"""Transactional (system) email: verification etc. Falls back to logging in development."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("jobapply.mailer")


def send_system_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if not s.system_smtp_host:
        log.info("system email (not sent; SMTP not configured) to=%s subject=%s", to, subject)
        return False
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = s.system_email_from, to, subject
    m.set_content(body)
    try:
        with smtplib.SMTP(s.system_smtp_host, s.system_smtp_port, timeout=15) as c:
            c.starttls()
            if s.system_smtp_user:
                c.login(s.system_smtp_user, s.system_smtp_password or "")
            c.send_message(m)
        return True
    except (smtplib.SMTPException, OSError):
        log.exception("system email failed")
        return False
