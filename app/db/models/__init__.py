# Імпорт усіх моделей реєструє їх у Base.metadata - на це спирається Alembic
from app.db.models.check import Check
from app.db.models.incident import Incident
from app.db.models.monitor import Monitor

__all__ = ["Check", "Incident", "Monitor"]
