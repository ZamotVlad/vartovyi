from fastapi import APIRouter, Response

from app.api.deps import StatusPageServiceDep
from app.schemas.check import StatusPageRead
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/status", tags=["status page"])


@router.get(
    "/{slug}",
    response_model=StatusPageRead,
    summary="Публічний статус моніторів користувача",
    responses={404: {"model": ErrorResponse}},
)
async def get_status_page(
    slug: str, response: Response, status_pages: StatusPageServiceDep
) -> StatusPageRead:
    # Публічна сторінка може отримати сплеск трафіку під час аварії: даємо кешувати
    response.headers["Cache-Control"] = "public, max-age=30"
    return await status_pages.get(slug)
