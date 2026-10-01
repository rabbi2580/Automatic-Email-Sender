from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class DeliveryError(Exception):
    def __init__(self, reason: str, retryable: bool = False, needs_reauth: bool = False):
        super().__init__(reason)
        self.reason, self.retryable, self.needs_reauth = reason, retryable, needs_reauth


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class OutgoingEmail:
    from_address: str
    from_name: str
    to: str
    subject: str
    body: str
    attachments: list[Attachment] = field(default_factory=list)


class DeliveryChannel(ABC):
    """A way of delivering an application. New channels (job-board APIs, ATS) implement this and register themselves."""

    name: str = "base"

    @abstractmethod
    def send(self, credentials: dict, message: OutgoingEmail) -> str | None:
        """Send and return the provider message id (if any). Raise DeliveryError on failure."""

    def verify(self, credentials: dict) -> None:
        """Optional connectivity check performed when an account is connected."""


def build_mime(msg: OutgoingEmail):
    from email.message import EmailMessage
    from email.utils import formataddr, make_msgid

    m = EmailMessage()
    m["From"] = formataddr((msg.from_name, msg.from_address)) if msg.from_name else msg.from_address
    m["To"] = msg.to
    m["Subject"] = msg.subject.replace("\n", " ").replace("\r", " ")  # header-injection safe
    m["Message-ID"] = make_msgid(domain=msg.from_address.split("@")[-1])
    m.set_content(msg.body)
    for a in msg.attachments:
        maintype, _, subtype = a.content_type.partition("/")
        m.add_attachment(a.data, maintype=maintype or "application", subtype=subtype or "octet-stream", filename=a.filename)
    return m
