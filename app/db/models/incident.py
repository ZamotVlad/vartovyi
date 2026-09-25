import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.monitor import Monitor


class Incident(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Період недоступності монітора. Відкритий, поки resolved_at порожній."""

    __tablename__ = "incidents"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        # Гарантія на рівні БД: не більше одного відкритого інциденту на монітор
        Index(
            "uq_incidents_monitor_id_open",
            "monitor_id",
            unique=True,
            postgresql_where="resolved_at IS NULL",
        ),
        Index("ix_incidents_monitor_id_started_at", "monitor_id", "started_at"),
    )

    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)

    monitor: Mapped["Monitor"] = relationship(back_populates="incidents")

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None
