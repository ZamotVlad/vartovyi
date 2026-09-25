from contextvars import ContextVar

# Контекст живе в межах одного запиту, включно з усіма корутинами, які він запускає
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()
