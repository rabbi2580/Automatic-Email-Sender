from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, JSONType, Timestamps, UUIDPk, owner_fk


class InterviewPrep(Base, UUIDPk, Timestamps):
    __tablename__ = "interview_preps"
    user_id: Mapped[uuid.UUID] = owner_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("applications.id", ondelete="CASCADE"), unique=True, index=True)
    questions: Mapped[list] = mapped_column(JSONType, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CalendarEvent(Base, UUIDPk, Timestamps):
    __tablename__ = "calendar_events"
    user_id: Mapped[uuid.UUID] = owner_fk()
    application_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("applications.id", ondelete="SET NULL"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="local")
    external_id: Mapped[str | None] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(String(300))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="planned")
