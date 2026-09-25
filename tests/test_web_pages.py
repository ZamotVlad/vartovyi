from pathlib import Path

import pytest
from httpx import AsyncClient

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
