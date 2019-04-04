import warnings

from typing import TypeVar, ClassVar, Union, Optional, Callable, List, Iterator

from aioconductor import Component
from aiohttp import web, ClientSession
from yarl import URL


Func = TypeVar("Func")
Decorator = Callable[[Func], Func]


def route(method: str, path: str, **kwargs) -> Decorator:
    def decorator(f: Func) -> Func:
        f.http_route_info = {  # type: ignore
            "method": method,
            "path": path,
            "kwargs": kwargs,
        }
        return f

    return decorator


def middleware(order: int) -> Decorator:
    def decorator(f: Func) -> Func:
        f.http_middleware_info = {"order": order}  # type: ignore
        return web.middleware(f)

    return decorator


class RouteTable(Component):

    prefix: ClassVar[str] = ""

    def __init_subclass__(cls, *, prefix: str = "", **kw) -> None:
        super().__init_subclass__(**kw)
        cls.prefix = prefix

    def iter_routes(self, prefix: str = "") -> Iterator[web.RouteDef]:
        prefix = prefix.rstrip("/")
        for name in dir(self):
            if name.startswith("_"):
                continue
            attr = getattr(self, name)
            if isinstance(attr, RouteTable):
                yield from attr.iter_routes(f"{prefix}/{attr.prefix.lstrip('/')}")
            else:
                try:
                    info = attr.http_route_info
                except AttributeError:
                    pass
                else:
                    yield web.RouteDef(
                        method=info["method"],
                        path=f"{prefix}/{info['path'].lstrip('/')}",
                        handler=attr,
                        kwargs=info["kwargs"],
                    )


class Application(RouteTable):

    _instance: web.Application

    async def on_setup(self) -> None:
        middlewares = []
        applications: List["Application"] = []

        attrs = (getattr(self, name) for name in dir(self) if not name.startswith("_"))
        for attr in attrs:
            if hasattr(attr, "http_middleware_info"):
                middlewares.append(attr)
            elif isinstance(attr, Application):
                applications.append(attr)

        middlewares.sort(key=lambda m: m.http_middleware_info["order"])

        self._instance = web.Application(
            middlewares=middlewares,
            client_max_size=self.config.get("http.client_max_size", 1024 ** 2),
        )
        for app in applications:
            self._instance.add_subapp(app.prefix, app._instance)
        self._instance.router.add_routes(self.iter_routes())

    async def on_shutdown(self) -> None:
        del self._instance


class Server(Application):

    _runner: web.AppRunner
    _site: web.TCPSite
    _client: Optional["Client"]

    async def on_setup(self) -> None:
        await super().on_setup()

        self._runner = web.AppRunner(
            self._instance,
            # access_log_class=access_log_class,
            # access_log_format=access_log_format,
            # access_log=access_log,
        )
        await self._runner.setup()

        self._site = web.TCPSite(
            self._runner,
            host=self.config["http.host"],
            port=self.config["http.port"],
            backlog=self.config.get("http.backlog", 128),
            shutdown_timeout=self.config.get("http.shutdown_timeout", 60.0),
        )
        await self._site.start()

        self._client = None

    async def on_shutdown(self) -> None:
        if self._client is not None:
            await self._client.close()
        del self._client
        await self._runner.cleanup()
        del self._site
        del self._runner
        await super().on_shutdown()

    def get_client(self) -> "Client":
        if self._client is None:
            self._client = Client(
                self.config["http.host"], self.config["http.port"], loop=self.loop
            )
        return self._client


with warnings.catch_warnings():
    warnings.simplefilter("ignore")

    class Client(ClientSession):

        app_host: str
        app_port: int

        def __init__(self, host: str, port: int, **kw) -> None:
            self.app_host = host
            self.app_port = port
            super().__init__(**kw)

        def app_url(self, url: Union[str, URL]) -> Union[str, URL]:
            if isinstance(url, str) and "//:" not in url:
                return URL.build(
                    scheme="http", host=self.app_host, port=self.app_port, path=url
                )
            return url

        def _request(self, method: str, str_or_url: Union[str, URL], **kw):
            return super()._request(method, self.app_url(str_or_url), **kw)

        def _ws_connect(self, url: Union[str, URL], **kw):
            return super()._ws_connect(self.app_url(url), **kw)
