from __future__ import annotations

from app.services.delivery.base import DeliveryChannel
from app.services.delivery.oauth import GmailChannel, OutlookChannel
from app.services.delivery.smtp import SMTPChannel

_channels: dict[str, DeliveryChannel] = {"gmail": GmailChannel(), "outlook": OutlookChannel(), "smtp": SMTPChannel()}


def get_channel(name: str) -> DeliveryChannel:
    if name not in _channels:
        raise KeyError(name)
    return _channels[name]


def register_channel(name: str, channel: DeliveryChannel) -> None:
    """Plug in new channels (job-board APIs, ATS integrations, test doubles)."""
    _channels[name] = channel
