import asyncio
from functools import partial
from inspect import cleandoc
from typing import (
    cast,
    TypeVar,
    Type,
    ClassVar,
    Union,
    Dict,
    List,
    Tuple,
    NamedTuple,
    Any,
    Callable,
    Awaitable,
    Iterator,
)

import validx
from aioconductor import Component

from ..exc import BaseExc, BaseError
from .request import Request, Handler, Middleware
from .response import Response
from .exc import (
    RPCUnsupportedVersion,
    RPCUndefinedMethod,
    RPCInvalidParams,
    RPCInternalError,
    RPCDeprecatedVersion,
)


Func = TypeVar("Func")
Decorator = Callable[[Func], Func]


def handler(
    f: Func = None,
    *,
    shield: bool = True,
    raises: Union[Type[BaseError], Tuple[Type[BaseError], ...]] = (),
    schema: validx.Validator = None,
    **kw,
) -> Union[Func, Decorator]:
    def decorator(f: Func) -> Func:
        f.rpc_handler_info = dict(  # type: ignore
            shield=shield, raises=raises, schema=schema or validx.Dict({}), **kw
        )
        return f

    return decorator if f is None else decorator(f)


def middleware(order: int) -> Decorator:
    def decorator(f: Func) -> Func:
        f.rpc_middleware_info = {"order": order}  # type: ignore
        return f

    return decorator


class MethodDef(NamedTuple):
    name: str
    handler: Callable[..., Awaitable[Any]]
    namespaces: Tuple["Namespace", ...]


class Namespace(Component):

    enabled: bool = True

    _middlewares: List[Middleware]

    async def on_setup(self) -> None:
        self._middlewares = []
        attrs = (getattr(self, name) for name in dir(self) if not name.startswith("_"))
        for attr in attrs:
            if hasattr(attr, "rpc_middleware_info"):
                self._middlewares.append(attr)

        self._middlewares.sort(
            key=lambda m: m.rpc_middleware_info["order"]  # type: ignore
        )

    async def on_shutdown(self) -> None:
        del self._middlewares

    def iter_methods(
        self, namespaces: Tuple["Namespace", ...] = (), prefix: str = ""
    ) -> Iterator[MethodDef]:
        attrs = (
            (name, getattr(self, name))
            for name in dir(self)
            if not name.startswith("_")
        )
        for name, attr in attrs:
            if hasattr(attr, "rpc_handler_info"):
                yield MethodDef(f"{prefix}{name}", attr, namespaces)
            elif (
                isinstance(attr, Namespace)
                and not isinstance(attr, Dispatcher)
                and attr.enabled
            ):
                yield from attr.iter_methods(namespaces + (attr,), f"{name}.")


class Dispatcher(Namespace):

    _methods: Dict[str, MethodDef]

    async def on_setup(self) -> None:
        await super().on_setup()
        self._methods = {md.name: md for md in self.iter_methods()}

    async def on_shutdown(self) -> None:
        del self._methods
        await super().on_shutdown()

    async def dispatch(self, request: Request) -> Response:
        try:
            md = self._methods[request.method]
        except KeyError:
            raise RPCUndefinedMethod(
                method=request.method, version=request.meta.get("version")
            )

        request.handler = md.handler
        request.handler_info = md.handler.rpc_handler_info  # type: ignore
        request.middlewares.extend(self._middlewares)
        for namespace in md.namespaces:
            request.middlewares.extend(namespace._middlewares)

        try:
            request.params = request.handler_info["schema"](request.params)
        except validx.exc.ValidationError as e:
            raise RPCInvalidParams(
                reason=self.format_schema_error(e),
                method=request.method,
                version=request.meta.get("version"),
            )

        async def wrapper(request: Request) -> Response:
            try:
                params = dict(request.params, **request.injections)
                aw = request.handler(**params)  # type: ignore
                if request.handler_info["shield"]:
                    aw = asyncio.shield(aw, loop=self.loop)
                result = await aw
                return request.response(result=result)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if isinstance(e, request.handler_info["raises"]) and isinstance(
                    e, BaseError
                ):
                    e.data.update(
                        method=request.method, version=request.meta.get("version")
                    )
                    # only exceptions explicitly declared by handler
                    # and derived from BaseError
                    raise
                self.logger.exception("Unexpected exception")
                raise RPCInternalError(
                    method=request.method, version=request.meta.get("version")
                )

        handler: Handler = wrapper
        for middleware in reversed(request.middlewares):
            handler = cast(Handler, partial(middleware, handler))

        return await handler(request)

    def format_schema_error(self, error: validx.exc.ValidationError) -> Dict[str, str]:
        return dict(validx.exc.format_error(error))

    @handler(shield=False, builtin=True)
    async def list_methods(self) -> List[Dict[str, Any]]:
        """List methods provided by API/Version"""
        result = []
        for method_def in self._methods.values():
            info = dict(
                method_def.handler.rpc_handler_info,  # type: ignore
                name=method_def.name,
                description=cleandoc(method_def.handler.__doc__ or ""),
            )
            info["schema"] = info["schema"].dump()
            info["raises"] = (
                [e.code for e in info["raises"]]
                if isinstance(info["raises"], tuple)
                else [info["raises"].code]
            )
            result.append(info)
        result.sort(key=lambda e: e["name"])
        return result

    @handler(shield=False, builtin=True)
    async def list_exceptions(self) -> List[Dict[str, Any]]:
        """List exceptions defined within API"""
        result = []
        for code, exc_class in BaseExc.registry.items():
            result.append(
                {
                    "code": code,
                    "message": exc_class.message,
                    "description": cleandoc(exc_class.__doc__ or ""),
                }
            )
        result.sort(key=lambda e: e["code"])
        return result


class Version(NamedTuple):
    major: int
    minor: int


class APIVersion(Dispatcher):
    version: ClassVar[Version]
    deprecated: ClassVar[bool] = False

    def __init_subclass__(
        cls, *, version: Tuple[int, int], deprecated: bool = False, **kw
    ):
        super().__init_subclass__(**kw)
        cls.version = Version(*version)
        cls.deprecated = deprecated

    @middleware(100)
    async def set_version_info(self, handler: Handler, request: Request) -> Response:
        response = await handler(request)
        response.meta.setdefault("version", self.version)
        if self.deprecated:
            response.warnings.append(RPCDeprecatedVersion())
        return response


class API(Dispatcher):

    _versions: Dict[int, Dict[int, APIVersion]]

    async def on_setup(self) -> None:
        await super().on_setup()
        versions = [v for v in self.depends_on if isinstance(v, APIVersion)]
        versions.sort(key=lambda v: v.version)
        self._versions = {}
        for v in versions:
            majors = self._versions.setdefault(v.version.major, {})
            majors[v.version.minor] = v

    async def on_shutdown(self) -> None:
        del self._versions
        await super().on_shutdown()

    async def dispatch(self, request: Request) -> Response:
        version = request.meta.setdefault("version", None)
        if version is None:
            return await super().dispatch(request)

        context: APIVersion
        try:
            majors = self._versions[version[0]]
        except KeyError:
            # Major version must be equal to requested one
            raise RPCUnsupportedVersion(version=version)
        try:
            context = majors[version[1]]
        except KeyError:
            # Minor version must be equal to or greather than requested one
            for minor, api_version in majors.items():
                if minor > version[1]:
                    context = api_version
                    break
            else:
                raise RPCUnsupportedVersion(version=request.meta["version"])

        request.meta["version"] = context.version
        request.middlewares.extend(self._middlewares)
        return await context.dispatch(request)

    @handler(shield=False, builtin=True)
    async def list_versions(self) -> List[Dict[str, Any]]:
        """List supported API versions"""
        result = []
        for majors in self._versions.values():
            for minor in majors.values():
                result.append(
                    {
                        "version": minor.version,
                        "deprecated": minor.deprecated,
                        "description": cleandoc(minor.__doc__ or ""),
                    }
                )
        return result
