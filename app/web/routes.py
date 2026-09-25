from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

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


# Публічні сторінки, які варто індексувати. Панель і службові - ні
INDEXABLE = ("/", "/login", "/register")


@router.get("/robots.txt")
async def robots(request: Request) -> PlainTextResponse:
    base = str(request.base_url).rstrip("/")
    body = f"User-agent: *\nDisallow: /api/\nDisallow: /dashboard\nSitemap: {base}/sitemap.xml\n"
    return PlainTextResponse(body)


@router.get("/sitemap.xml")
async def sitemap(request: Request) -> Response:
    base = str(request.base_url).rstrip("/")
    urls = "".join(f"<url><loc>{base}{path}</loc></url>" for path in INDEXABLE)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )
    return Response(body, media_type="application/xml")
