from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(include_in_schema=False)


@router.get("/status/{slug}")
async def status_page(slug: str) -> FileResponse:
    # Одна статична сторінка на всі slug: дані вона бере з /api/v1/status/{slug}
    return FileResponse(STATIC_DIR / "status" / "index.html")
