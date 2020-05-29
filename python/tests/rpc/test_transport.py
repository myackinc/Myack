import asyncio
from datetime import date, timedelta

import pytest
import validx
import aiohttp

from myack.http import Server
from myack.rpc.transport import HTTPRoutes
from myack.rpc.api import API, APIVersion, handler
from myack.rpc.exc import (
    RPCParseError,
    RPCInvalidRequest,
    RPCInternalError,
    RPCUndefinedMethod,
    RPCDeprecatedVersion,
)
from myack.exc import BaseExc


@pytest.mark.asyncio
async def test_routes(conductor, unused_tcp_port):
    class TestAPI(API):
        @handler(schema=validx.Dict({"x": validx.Int(), "y": validx.Int()}))
        async def sum(self, x, y):
            return x + y

    class RPCRoutes(HTTPRoutes, api=TestAPI, prefix="/rpc"):
        pass

    class App(Server):
        rpc: RPCRoutes

    app = await conductor(
        App, config={"http.host": "localhost", "http.port": unused_tcp_port}
    )
    http_client = app.get_client()
    client = app.rpc.get_client(http_client)

    assert await client.request("sum", x=1, y=2) == 3
    assert await client.batch(
        {"method": "sum", "params": {"x": 1, "y": 2}},
        {"method": "sum", "params": {"x": 3, "y": 4}},
    ) == [3, 7]

    async with http_client.get("/rpc/healthcheck") as response:
        assert response.status == 204


@pytest.mark.asyncio
async def test_disconnection(conductor, unused_tcp_port):

    call_hanging = asyncio.Event()

    class TestAPI(API):
        @handler(
            shield=False, schema=validx.Dict({"x": validx.Int(), "y": validx.Int()})
        )
        async def sum(self, x, y):
            call_hanging.set()
            await asyncio.sleep(60, loop=self.loop)
            return x + y

    class RPCRoutes(HTTPRoutes, api=TestAPI, prefix="/rpc"):
        pass

    class App(Server):
        rpc: RPCRoutes

    app = await conductor(
        App, config={"http.host": "localhost", "http.port": unused_tcp_port}
    )
    client = app.rpc.get_client(app.get_client())

    task = app.loop.create_task(client.request("sum", x=1, y=2))
    await call_hanging.wait()

    await client.http_client.close()
    with pytest.raises(aiohttp.client_exceptions.ServerDisconnectedError):
        await task


@pytest.mark.asyncio
async def test_errors(conductor, unused_tcp_port):
    class TestAPI(API):
        @handler(schema=validx.Dict({"x": validx.Int(), "y": validx.Int()}))
        async def sum(self, x, y):
            return x + y

        @handler
        async def unserializable(self) -> object:
            # Returns unserializable object
            return object()

    class RPCRoutes(HTTPRoutes, api=TestAPI, prefix="/rpc"):
        pass

    class App(Server):
        rpc: RPCRoutes

    app = await conductor(
        App, config={"http.host": "localhost", "http.port": unused_tcp_port}
    )
    client = app.rpc.get_client(app.get_client())

    with pytest.raises(RPCUndefinedMethod):
        await client.request("undefined")

    result = await client.batch(
        {"method": "undefined"}, {"method": "sum", "params": {"x": 1, "y": 2}}
    )
    assert isinstance(result[0], RPCUndefinedMethod)
    assert result[1] == 3

    with pytest.raises(RPCInternalError):
        await client.request("unserializable")

    async with client.http_client.post(
        client.endpoint, data=b"invalid_json"
    ) as response:
        response = client.serializer.loadb(await response.read())
        error = response["error"]
        exc = BaseExc.dispatch(error["code"], error["message"], **error["data"])
        assert isinstance(exc, RPCParseError)
        assert exc.data["reason"] == "Parse error at offset 0: Invalid value."

    request_body = client.serializer.dumpb(
        {"method": "div", "params": {"x": 4, "y": 2}}
    )
    async with client.http_client.post(client.endpoint, data=request_body) as response:
        response = client.serializer.loadb(await response.read())
        error = response["error"]
        exc = BaseExc.dispatch(error["code"], error["message"], **error["data"])
        assert isinstance(exc, RPCInvalidRequest)
        assert exc.data["reason"]["id"] == "Required key is not provided."


@pytest.mark.parametrize("retire", [None, date.today() + timedelta(days=30)])
@pytest.mark.asyncio
async def test_warnings(conductor, unused_tcp_port, retire):
    class V10(APIVersion, version=(1, 0), deprecated=True, retire=retire):
        @handler(schema=validx.Dict({"x": validx.Int(), "y": validx.Int()}))
        async def sum(self, x, y):
            return x + y

    class TestAPI(API):
        v10: V10

    class RPCRoutes(HTTPRoutes, api=TestAPI, prefix="/rpc"):
        pass

    class App(Server):
        rpc: RPCRoutes

    app = await conductor(
        App, config={"http.host": "localhost", "http.port": unused_tcp_port}
    )
    client = app.rpc.get_client(app.get_client())

    with pytest.warns(RPCDeprecatedVersion) as info:
        assert await client.request("sum", {"version": [1, 0]}, x=1, y=2) == 3
    assert len(info) == 1
    assert info[0].message == RPCDeprecatedVersion(retire=retire)

    with pytest.warns(RPCDeprecatedVersion) as info:
        assert await client.batch(
            {"method": "sum", "meta": {"version": [1, 0]}, "params": {"x": 1, "y": 2}},
            {"method": "sum", "meta": {"version": [1, 0]}, "params": {"x": 3, "y": 5}},
        ) == [3, 8]
    assert len(info) == 2
    assert info[0].message == RPCDeprecatedVersion(retire=retire)
    assert info[1].message == RPCDeprecatedVersion(retire=retire)
