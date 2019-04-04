import inspect
from typing import Optional, Callable, Awaitable, ClassVar, Any, Dict, List

import validx
from cached_property import cached_property

from ..exc import BaseError, BaseWarning
from .exc import RPCInvalidRequest
from .response import Response


Handler = Callable[["Request"], Awaitable[Response]]
Middleware = Callable[[Handler, "Request"], Awaitable[Response]]


class Request:

    schema: ClassVar[validx.Validator] = validx.Dict(
        {
            "id": validx.Int(),
            "method": validx.Str(encoding="ascii"),
            "params": validx.Dict(extra=(validx.Str(), validx.Any())),
            "meta": validx.Dict(
                {
                    "version": validx.Tuple(
                        validx.Int(min=0), validx.Int(min=0), nullable=True
                    ),
                },
                optional=("version",),
                extra=(validx.Str(), validx.Any()),
            ),
        },
        defaults={"params": {}, "meta": {}},
    )

    id: int
    method: str
    meta: Dict[str, Any]
    params: Dict[str, Any]

    middlewares: List[Middleware]
    injections: Dict[str, Any]

    handler: Optional[Callable[..., Awaitable[Any]]]
    handler_info: Dict[str, Any]

    def __init__(
        self,
        id: int,
        method: str,
        meta: Dict[str, Any] = None,
        params: Dict[str, Any] = None,
    ) -> None:
        self.id = id
        self.method = method
        self.meta = meta if meta is not None else {}
        self.params = params if params is not None else {}

        self.middlewares = []
        self.injections = {}

        self.handler = None
        self.handler_info = {}

    @classmethod
    def load(cls, payload: Dict[str, Any]) -> "Request":
        try:
            return cls(**cls.schema(payload))
        except validx.exc.ValidationError as e:
            raise RPCInvalidRequest(reason=cls.format_schema_error(e))

    @classmethod
    def format_schema_error(cls, error: validx.exc.ValidationError) -> Dict[str, str]:
        return dict(validx.exc.format_error(error))

    @cached_property
    def handler_signature(self) -> inspect.Signature:
        assert self.handler is not None
        return inspect.signature(self.handler)

    def response(
        self,
        result: Any = None,
        meta: Dict[str, Any] = None,
        error: BaseError = None,
        warnings: List[BaseWarning] = None,
    ) -> Response:
        return Response(
            id=self.id, meta=meta, result=result, error=error, warnings=warnings
        )
