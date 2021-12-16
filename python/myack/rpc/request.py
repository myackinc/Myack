import inspect
import typing as t

import validx
from cached_property import cached_property

from ..exc import BaseError, BaseWarning
from .exc import RPCInvalidRequest
from .response import Response


Handler = t.Callable[["Request"], t.Awaitable[Response]]
Middleware = t.Callable[[Handler, "Request"], t.Awaitable[Response]]


class Request:

    schema: t.ClassVar[validx.Validator] = validx.Dict(
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
    meta: t.Dict[str, t.Any]
    params: t.Dict[str, t.Any]

    middlewares: t.List[Middleware]
    injections: t.Dict[str, t.Any]

    handler: t.Optional[t.Callable[..., t.Awaitable[t.Any]]]
    handler_info: t.Dict[str, t.Any]

    def __init__(
        self,
        id: int,
        method: str,
        meta: t.Dict[str, t.Any] = None,
        params: t.Dict[str, t.Any] = None,
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
    def load(cls, payload: t.Dict[str, t.Any]) -> "Request":
        try:
            return cls(**cls.schema(payload))
        except validx.exc.ValidationError as e:
            raise RPCInvalidRequest(reason=cls.format_schema_error(e))

    @classmethod
    def format_schema_error(cls, error: validx.exc.ValidationError) -> t.Dict[str, str]:
        return dict(validx.exc.format_error(error))

    @cached_property
    def handler_signature(self) -> inspect.Signature:
        assert self.handler is not None
        return inspect.signature(self.handler)

    def response(
        self,
        result: t.Any = None,
        meta: t.Dict[str, t.Any] = None,
        error: BaseError = None,
        warnings: t.List[BaseWarning] = None,
    ) -> Response:
        return Response(
            id=self.id, meta=meta, result=result, error=error, warnings=warnings
        )
