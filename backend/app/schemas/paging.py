from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """One page of a list: `items` from the requested offset, and `total`,
    how many match across all pages."""

    items: list[T]
    total: int
