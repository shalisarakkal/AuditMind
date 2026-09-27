from enum import Enum
from typing import TypeVar

from sqlalchemy import Enum as SqlEnum

E = TypeVar("E", bound=Enum)


def str_enum(enum_cls: type[E]) -> SqlEnum:
    """Stores a Python str-Enum as a plain VARCHAR (native_enum=False) while
    round-tripping to the actual enum member on read, instead of a bare str."""
    return SqlEnum(
        enum_cls,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )
