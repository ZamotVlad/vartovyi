from functools import cache

from app.web.routes import PAGES_DIR


def wants_html(path: str, accept: str) -> bool:
    """Браузерна навігація поза API отримує сторінку, решта - JSON."""
    return not path.startswith("/api/") and "text/html" in accept


@cache
def error_page(status_code: int) -> bytes:
    return (PAGES_DIR / f"{status_code}.html").read_bytes()
