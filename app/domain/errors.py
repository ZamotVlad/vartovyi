from typing import ClassVar


class DomainError(Exception):
    """Базова помилка бізнес-правил. Про HTTP нічого не знає."""

    code: ClassVar[str] = "domain_error"
    message: ClassVar[str] = "Порушено бізнес-правило"

    def __init__(self, message: str | None = None) -> None:
        self.detail = message or self.message
        super().__init__(self.detail)


class EmailAlreadyRegisteredError(DomainError):
    code = "email_already_registered"
    message = "Користувач з таким email уже існує"


class InvalidCredentialsError(DomainError):
    code = "invalid_credentials"
    message = "Невірний email або пароль"


class InvalidTokenError(DomainError):
    code = "invalid_token"
    message = "Токен недійсний, прострочений або відкликаний"


class InactiveUserError(DomainError):
    code = "inactive_user"
    message = "Обліковий запис деактивовано"


class ApiKeyNotFoundError(DomainError):
    code = "api_key_not_found"
    message = "API-ключ не знайдено"


class MonitorNotFoundError(DomainError):
    code = "monitor_not_found"
    message = "Монітор не знайдено"


class InvalidMonitorConfigError(DomainError):
    code = "invalid_monitor_config"
    message = "Некоректні налаштування монітора"
