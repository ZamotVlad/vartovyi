import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.check import Check
    from app.db.models.incident import Incident


class Monitor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "monitors"
    # Серверні значення (created_at, updated_at) повертаються через RETURNING,
    # інакше доступ до них після flush спричинить lazy load в async-контексті
    __mapper_args__ = {"eager_defaults": True}

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2048))
    interval_seconds: Mapped[int] = mapped_column(Integer)
    timeout_ms: Mapped[int] = mapped_column(Integer)
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    max_response_ms: Mapped[int | None] = mapped_column(Integer)
    keyword: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Показувати на публічній сторінці статусу власника
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Денормалізація: планувальнику не треба агрегувати checks, щоб знайти прострочені
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    checks: Mapped[list["Check"]] = relationship(
        back_populates="monitor", cascade="all, delete-orphan", passive_deletes=True
    )
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="monitor", cascade="all, delete-orphan", passive_deletes=True
    )
