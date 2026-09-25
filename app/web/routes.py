from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).parent / "static"
PAGES_DIR = STATIC_DIR / "pages"

router = APIRouter(include_in_schema=False)


def _page(path: Path) -> FileResponse:
    # no-cache: після деплою браузер не покаже стару розмітку зі старими скриптами
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


@router.get("/")
async def landing() -> FileResponse:
    return _page(PAGES_DIR / "index.html")


@router.get("/login")
async def login() -> FileResponse:
    return _page(PAGES_DIR / "login.html")


@router.get("/register")
async def register() -> FileResponse:
    return _page(PAGES_DIR / "register.html")


@router.get("/dashboard")
async def dashboard() -> FileResponse:
    # Токен живе в localStorage, тож перевірку і редірект на /login робить сам JS
    return _page(PAGES_DIR / "dashboard.html")


@router.get("/status/{slug}")
async def status_page(slug: str) -> FileResponse:
    # Одна статична сторінка на всі slug: дані вона бере з /api/v1/status/{slug}
    return _page(STATIC_DIR / "status" / "index.html")
