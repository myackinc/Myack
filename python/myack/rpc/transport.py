import asyncio
import sys
import warnings
import typing as t
from random import randint

from aiohttp import web

from ..serializer import Serializer
from ..http import RouteTable, Client as HTTPClient, route
from ..exc import BaseExc, BaseError
from .api import API
from .request import Request, TransportInfo
from .response import Response
from .exc import RPCParseError, RPCInvalidRequest, RPCInternalError


class HTTPRoutes(RouteTable):

    api: API
    serializer: Serializer

    _client: t.Optional["Client"]

    def __init_subclass__(cls, *, api: t.Type[API], **kw) -> None:
        cls.__annotations__["api"] = api
        super().__init_subclass__(**kw)

    async def on_setup(self) -> None:
        self._client = None

    async def on_shutdown(self) -> None:
        del self._client

    def get_client(self, http_client: HTTPClient, endpoint: str = None) -> "Client":
        if self._client is None:
            self._client = Client(
                endpoint=endpoint or f"{self.prefix.rstrip('/')}/",
                serializer=self.serializer,
                http_client=http_client,
            )
        return self._client

    @route("GET", "/healthcheck")
    async def healthcheck(self, http_request: web.Request) -> web.Response:
        return web.Response(status=204)

    @route("POST", "/")
    async def post(self, http_request: web.Request) -> web.Response:
        try:
            json_request = await http_request.read()
            json_response = await self.handle_json(json_request, http_request.headers)
            return web.Response(content_type="application/json", body=json_response)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception:  # pragma: no cover
            self.logger.exception("Unexpected exception")
            raise web.HTTPInternalServerError()

    async def handle_json(
        self,
        json_request: bytes,
        http_headers: TransportInfo,
    ) -> bytes:
        # Parse request
        try:
            raw_request = self.serializer.loadb(json_request)
        except (ValueError, TypeError) as e:
            return self.serializer.dumpb(Response(error=RPCParseError(reason=str(e))))

        # Handle request
        if isinstance(raw_request, list):
            response = await asyncio.gather(
                *(self.handle_raw(r, http_headers) for r in raw_request), loop=self.loop
            )
        else:
            response = await self.handle_raw(raw_request, http_headers)  # type: ignore

        # Serialize response
        try:
            return self.serializer.dumpb(response)
        except (ValueError, TypeError):
            self.logger.exception("Unexpected exception")
            return self.serializer.dumpb(Response(error=RPCInternalError()))

    async def handle_raw(
        self,
        raw_request: t.Dict[str, t.Any],
        http_headers: TransportInfo,
    ) -> Response:
        try:
            request = Request.load(raw_request, transport_info=http_headers)
        except RPCInvalidRequest as e:
            request_id = (
                raw_request["id"]
                if isinstance(raw_request, dict)
                and isinstance(raw_request.get("id"), int)
                else None
            )
            return Response(id=request_id, error=e)
        try:
            return await self.api.dispatch(request)
        except BaseError as e:
            return request.response(error=e)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover
            self.logger.exception("Unexpected exception")
            return request.response(error=RPCInternalError())


class Client:

    endpoint: str

    serializer: Serializer
    http_client: HTTPClient

    def __init__(
        self, endpoint: str, serializer: Serializer, http_client: HTTPClient
    ) -> None:
        self.endpoint = endpoint
        self.serializer = serializer
        self.http_client = http_client

    def make_request(
        self,
        method: str,
        meta: t.Dict[str, t.Any] = None,
        params: t.Dict[str, t.Any] = None,
    ) -> t.Dict[str, t.Any]:
        return {
            "id": randint(0, sys.maxsize),
            "method": method,
            "meta": meta or {},
            "params": params or {},
        }

    def make_response(self, response_body: bytes) -> t.Any:
        response_data = self.serializer.loadb(response_body)
        if isinstance(response_data, list):
            result = []
            for resp in response_data:
                for warning in resp["warnings"]:
                    warnings.warn(
                        t.cast(
                            Warning,
                            BaseExc.dispatch(
                                warning["code"], warning["message"], **warning["data"]
                            ),
                        )
                    )
                error = resp["error"]
                if error is not None:
                    result.append(
                        BaseExc.dispatch(
                            error["code"], error["message"], **error["data"]
                        )
                    )
                else:
                    result.append(resp["result"])
            return result
        else:
            for warning in response_data["warnings"]:
                warnings.warn(
                    t.cast(
                        Warning,
                        BaseExc.dispatch(
                            warning["code"], warning["message"], **warning["data"]
                        ),
                    )
                )
            error = response_data["error"]
            if error is not None:
                raise BaseExc.dispatch(error["code"], error["message"], **error["data"])
            return response_data["result"]

    async def request(
        self,
        method: str,
        meta: t.Dict[str, t.Any] = None,
        **params,
    ) -> t.Dict[str, t.Any]:
        request_body = self.serializer.dumpb(self.make_request(method, meta, params))
        async with self.http_client.post(self.endpoint, data=request_body) as response:
            response.raise_for_status()
            response_body = await response.read()
            return self.make_response(response_body)

    async def batch(self, *request_data: t.Dict[str, t.Any]) -> t.List[t.Any]:
        request_data = [self.make_request(**r) for r in request_data]  # type: ignore
        request_body = self.serializer.dumpb(request_data)
        async with self.http_client.post(self.endpoint, data=request_body) as response:
            response.raise_for_status()
            response_body = await response.read()
            return self.make_response(response_body)
