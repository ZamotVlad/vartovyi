from sqlalchemy.ext.asyncio import AsyncSession


class SqlRepository:
    """Доступ до даних без керування транзакцією.

    Репозиторій робить flush, щоб отримати згенеровані БД значення,
    але ніколи не commit: межу транзакції визначає сервіс.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
