from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.web.routes import STATIC_DIR

PAGES = ["/", "/login", "/register", "/dashboard", "/status/demo"]


@pytest.mark.parametrize("path", PAGES)
async def test_page_is_served_without_auth(client: AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", PAGES)
async def test_every_page_has_brand_mark_and_favicon(client: AsyncClient, path: str) -> None:
    html = (await client.get(path)).text
    assert html.count("<head>") == 1
    assert 'class="brand"' in html
    assert "/static/favicon.svg" in html
    assert "/static/css/fonts.css" in html
    assert "/static/css/app.css" in html
    assert "fonts.googleapis.com" not in html


@pytest.mark.parametrize(
    "asset",
    ["css/app.css", "js/api.js", "js/auth.js", "js/dashboard.js", "js/landing.js", "favicon.svg"],
)
async def test_assets_are_served(client: AsyncClient, asset: str) -> None:
    assert (await client.get(f"/static/{asset}")).status_code == 200


async def test_dashboard_without_token_redirects_to_login(client: AsyncClient) -> None:
    # Токен зберігається в localStorage, тому редірект робить скрипт сторінки
    html = (await client.get("/dashboard")).text
    script = (await client.get("/static/js/dashboard.js")).text

    assert "/static/js/dashboard.js" in html
    assert 'id="app" hidden' in html  # панель не видно до перевірки токена
    assert "if (!Api.tokens.access())" in script
    assert "window.location.replace(`/login?next=" in (await client.get("/static/js/api.js")).text


def test_scripts_never_insert_html() -> None:
    # Усі дані з бекенду виводяться як текст
    for script in Path(STATIC_DIR).rglob("*.js"):
        assert "innerHTML" not in script.read_text(), script
        assert "insertAdjacentHTML" not in script.read_text(), script


async def test_unknown_page_in_browser_gets_html_404(client: AsyncClient) -> None:
    response = await client.get("/no-such-page", headers={"Accept": "text/html"})

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "HTTP 404" in response.text


async def test_unknown_api_path_stays_json_even_for_browser(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nope", headers={"Accept": "text/html"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_crash_in_browser_gets_html_500() -> None:
    app = create_app(Settings())

    @app.get("/explode", include_in_schema=False)
    async def explode() -> None:
        raise RuntimeError("boom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        page = await http.get("/explode", headers={"Accept": "text/html"})
        api = await http.get("/explode", headers={"Accept": "application/json"})

    assert page.status_code == api.status_code == 500
    assert "HTTP 500" in page.text
    assert "boom" not in page.text
    assert api.json()["error"]["code"] == "internal_error"


def test_error_pages_do_not_depend_on_scripts() -> None:
    # Сторінка 500 має працювати, навіть коли щось зламано: тільки HTML і CSS
    for name in ("404.html", "500.html"):
        assert "<script" not in (STATIC_DIR / "pages" / name).read_text()


async def test_robots_hides_private_areas_and_points_to_sitemap(client: AsyncClient) -> None:
    body = (await client.get("/robots.txt")).text
    assert "Disallow: /dashboard" in body
    assert "Disallow: /api/" in body
    assert "Sitemap: http://test/sitemap.xml" in body


async def test_sitemap_lists_only_public_pages(client: AsyncClient) -> None:
    response = await client.get("/sitemap.xml")
    assert response.headers["content-type"].startswith("application/xml")
    assert "<loc>http://test/register</loc>" in response.text
    assert "dashboard" not in response.text


@pytest.mark.parametrize("path", ["/", "/login", "/register", "/status/demo"])
async def test_public_pages_have_description(client: AsyncClient, path: str) -> None:
    assert '<meta name="description"' in (await client.get(path)).text


async def test_dashboard_is_not_indexed(client: AsyncClient) -> None:
    assert '<meta name="robots" content="noindex">' in (await client.get("/dashboard")).text
