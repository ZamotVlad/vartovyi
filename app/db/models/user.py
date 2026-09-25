from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.api_key import ApiKey


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __mapper_args__ = {"eager_defaults": True}

    # Зберігається в нижньому регістрі, нормалізацію робить сервіс
    email: Mapped[str] = mapped_column(String(320), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Адреса публічної сторінки статусу /status/{slug}. None - сторінки немає
    status_slug: Mapped[str | None] = mapped_column(String(50), unique=True)

    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
