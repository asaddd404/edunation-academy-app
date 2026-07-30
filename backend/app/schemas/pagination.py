import math
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int

    @classmethod
    def of(cls, items: list[T], total: int, page: int, per_page: int) -> "Page[T]":
        return cls(items=items, total=total, page=page, per_page=per_page, pages=math.ceil(total / per_page) if per_page else 0)
