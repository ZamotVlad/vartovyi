# Імпорт усіх моделей реєструє їх у Base.metadata - на це спирається Alembic
from app.db.models.api_key import ApiKey
from app.db.models.check import Check
from app.db.models.incident import Incident
from app.db.models.monitor import Monitor
from app.db.models.user import User

__all__ = ["ApiKey", "Check", "Incident", "Monitor", "User"]
