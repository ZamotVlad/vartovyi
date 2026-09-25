from typing import ClassVar


class DomainError(Exception):
    """Базова помилка бізнес-правил. Про HTTP нічого не знає.

    Підкласи-категорії нижче описують суть помилки. Відображення категорії
    на HTTP-статус живе в шарі API, тож домен лишається придатним і для
    Celery-задач чи CLI.
    """

    code: ClassVar[str] = "domain_error"
    message: ClassVar[str] = "Порушено бізнес-правило"

    def __init__(self, message: str | None = None) -> None:
        self.detail = message or self.message
        super().__init__(self.detail)


class NotFoundError(DomainError):
    code = "not_found"
    message = "Ресурс не знайдено"


class ConflictError(DomainError):
    code = "conflict"
    message = "Конфлікт з поточним станом"


class AuthenticationError(DomainError):
    code = "authentication_failed"
    message = "Потрібна автентифікація"


class PermissionDeniedError(DomainError):
    code = "permission_denied"
    message = "Недостатньо прав"


class RuleViolationError(DomainError):
    code = "rule_violation"
    message = "Дані суперечать бізнес-правилам"


class EmailAlreadyRegisteredError(ConflictError):
    code = "email_already_registered"
    message = "Користувач з таким email уже існує"


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    message = "Невірний email або пароль"


class InvalidTokenError(AuthenticationError):
    code = "invalid_token"
    message = "Токен недійсний, прострочений або відкликаний"


class NotAuthenticatedError(AuthenticationError):
    code = "not_authenticated"
    message = "Потрібен Bearer-токен або заголовок X-API-Key"


class InactiveUserError(PermissionDeniedError):
    code = "inactive_user"
    message = "Обліковий запис деактивовано"


class ApiKeyNotFoundError(NotFoundError):
    code = "api_key_not_found"
    message = "API-ключ не знайдено"


class MonitorNotFoundError(NotFoundError):
    code = "monitor_not_found"
    message = "Монітор не знайдено"


class InvalidMonitorConfigError(RuleViolationError):
    code = "invalid_monitor_config"
    message = "Некоректні налаштування монітора"
