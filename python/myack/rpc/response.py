import typing as t

from ..serializer import Serializable
from ..exc import BaseError, BaseWarning


class Response(Serializable):

    id: t.Optional[int]
    meta: t.Dict[str, t.Any]
    result: t.Any
    error: t.Optional[BaseError]
    warnings: t.List[BaseWarning]

    def __init__(
        self,
        id: int = None,
        meta: t.Dict[str, t.Any] = None,
        result: t.Any = None,
        error: BaseError = None,
        warnings: t.List[BaseWarning] = None,
    ) -> None:
        self.id = id
        self.meta = meta or {}
        self.result = result
        self.error = error
        self.warnings = warnings or []

    def dump(self) -> t.Dict[str, t.Any]:
        return {
            "id": self.id,
            "meta": self.meta,
            "result": self.result,
            "error": self.error,
            "warnings": self.warnings,
        }
