from pydantic import BaseModel

from app.schemas.common import ErrorDetail, ErrorResponse, Page


class Item(BaseModel):
    id: int
    title: str


def test_generic_page_carries_typed_items() -> None:
    page = Page[Item](
        items=[Item(id=1, title="перший")],
        total=1,
        limit=20,
        offset=0,
    )
    assert page.items[0].title == "перший"


def test_generic_page_validates_item_type() -> None:
    page = Page[Item].model_validate(
        {
            "items": [{"id": 7, "title": "з словника"}],
            "total": 1,
            "limit": 20,
            "offset": 0,
        }
    )
    assert isinstance(page.items[0], Item)


def test_error_response_shape() -> None:
    response = ErrorResponse(
        error=ErrorDetail(code="monitor_not_found", message="Монітор не знайдено")
    )
    assert response.model_dump()["error"]["code"] == "monitor_not_found"
