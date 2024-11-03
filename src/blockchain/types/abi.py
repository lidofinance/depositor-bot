from typing import Any, Self

from pydantic import BaseModel as _BaseModel
from pydantic.alias_generators import to_snake


class BaseModel(_BaseModel):
    def __init__(self, obj: Any = None, **data):
        if isinstance(obj, tuple) and hasattr(obj, '_asdict'):
            data = obj._asdict()

        new_data = {}

        for key, value in data.items():
            if isinstance(value, tuple) and hasattr(value, '_asdict'):
                new_data[to_snake(key)] = value._asdict()
            else:
                new_data[to_snake(key)] = value

        super().__init__(**new_data)

    @classmethod
    def from_list(cls, objects_list: list[Any]) -> list[Self]:
        return [cls(obj) for obj in objects_list]

    class Config:
        extra = 'allow'  # Allows additional fields without validation
