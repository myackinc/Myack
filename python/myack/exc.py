from typing import ClassVar, Type, Optional, Any, Dict

from .serializer import Serializable


class BaseExc(Exception, Serializable):
    """Base Exception"""

    registry: ClassVar[Dict[str, Type["BaseExc"]]] = {}

    code: ClassVar[str]
    message: Optional[str] = None
    data: Dict[str, Any]

    def __init_subclass__(cls, *, code: str) -> None:
        try:
            cls.code = f"{cls.code}.{code}"
        except AttributeError:
            cls.code = code
        assert (
            cls.code not in BaseExc.registry
        ), f"Code '{cls.code}' of {cls} conflicts with {BaseExc.registry[cls.code]}"
        BaseExc.registry[cls.code] = cls

    @classmethod
    def dispatch(cls, code: str, message: str = None, **data) -> "BaseExc":
        try:
            return BaseExc.registry[code](message, **data)
        except KeyError:
            return UndefinedExc(
                original={"code": code, "message": message, "data": data}
            )

    def __init__(self, message: str = None, **data) -> None:
        self.message = message or self.message
        self.data = data
        assert self.message is not None, "Empty exception message"
        super().__init__(self.code, self.message, self.data)

    def __eq__(self, other: Any) -> bool:
        return type(self) is type(other) and self.args == other.args

    def dump(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "data": self.data}


class UndefinedExc(BaseExc, code="undefined"):
    """Undefined exception"""

    message: str = "Undefined exception"


class BaseWarning(BaseExc, Warning, code="warning"):
    """Base class of warning exceptions"""


class BaseError(BaseExc, code="error"):
    """Base class of error exceptions"""
