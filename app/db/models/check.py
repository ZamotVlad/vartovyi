import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.domain.check import CheckStatus, FailureReason

if TYPE_CHECKING:
    from app.db.models.monitor import Monitor


def _values(enum_cls: type[CheckStatus] | type[FailureReason]) -> list[str]:
    return [member.value for member in enum_cls]


class Check(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Результат однієї перевірки. Незмінний запис, тільки вставка."""

    __tablename__ = "checks"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        # Основний шаблон читання: перевірки монітора за період, найновіші першими
        Index("ix_checks_monitor_id_created_at", "monitor_id", "created_at"),
    )

    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    # native_enum=False: VARCHAR замість типу Postgres, новий статус не потребує ALTER TYPE
    status: Mapped[CheckStatus] = mapped_column(
        Enum(CheckStatus, native_enum=False, length=20, values_callable=_values)
    )
    elapsed_ms: Mapped[float] = mapped_column(Float)
    status_code: Mapped[int | None] = mapped_column(Integer)
    failure: Mapped[FailureReason | None] = mapped_column(
        Enum(FailureReason, native_enum=False, length=30, values_callable=_values)
    )
    reason: Mapped[str | None] = mapped_column(Text)

    monitor: Mapped["Monitor"] = relationship(back_populates="checks")
