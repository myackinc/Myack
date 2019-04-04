from typing import Optional, Any, Dict, List

from ..serializer import Serializable
from ..exc import BaseError, BaseWarning


class Response(Serializable):

    id: Optional[int]
    meta: Dict[str, Any]
    result: Any
    error: Optional[BaseError]
    warnings: List[BaseWarning]

    def __init__(
        self,
        id: int = None,
        meta: Dict[str, Any] = None,
        result: Any = None,
        error: BaseError = None,
        warnings: List[BaseWarning] = None,
    ) -> None:
        self.id = id
        self.meta = meta or {}
        self.result = result
        self.error = error
        self.warnings = warnings or []

    def dump(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "meta": self.meta,
            "result": self.result,
            "error": self.error,
            "warnings": self.warnings,
        }
