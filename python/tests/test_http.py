import pytest
from aiohttp.web import Response, WebSocketResponse, WSMsgType

from myack.http import Server, Application, RouteTable, route, middleware


@pytest.mark.asyncio
async def test_http(conductor, unused_tcp_port):
    class NestedRoutes(RouteTable, prefix="/routes"):
        @route("GET", "/foo")
        async def foo(self, request):
            return Response(text="NestedRoutes.foo", content_type="text/plain")

    class NestedApp(Application, prefix="/app"):
        nested_routes: NestedRoutes

        @route("GET", "/foo")
        async def foo(self, request):
            return Response(text="NestedApp.foo", content_type="text/plain")

        @middleware(1)
        async def bar(self, request, handler):
            response = await handler(request)
            response.text = response.text + " + NestedApp.bar"
            return response

        @middleware(2)
        async def baz(self, request, handler):
            response = await handler(request)
            response.text = response.text + " + NestedApp.baz"
            return response

    class RootApp(Server):
        nested_app: NestedApp

        @route("GET", "/foo")
        async def foo(self, request):
            return Response(text="RootApp.foo", content_type="text/plain")

        @route("GET", "/ping-pong")
        async def ping_pong(self, request):
            ws = WebSocketResponse()
            await ws.prepare(request)
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    if msg.data == "close":
                        await ws.close()
                    elif msg.data == "ping":
                        await ws.send_str("pong")
            return ws

        @middleware(1)
        async def bar(self, request, handler):
            response = await handler(request)
            response.text = response.text + " + RootApp.bar"
            return response

        @middleware(2)
        async def baz(self, request, handler):
            response = await handler(request)
            response.text = response.text + " + RootApp.baz"
            return response

    app = await conductor(
        RootApp, config={"http.host": "localhost", "http.port": unused_tcp_port}
    )

    client = app.get_client()

    async with client.get("/foo") as response:
        assert await response.text() == "RootApp.foo + RootApp.baz + RootApp.bar"

    async with client.get("/app/foo") as response:
        assert await response.text() == (
            "NestedApp.foo + NestedApp.baz + NestedApp.bar + "
            "RootApp.baz + RootApp.bar"
        )

    async with client.get("/app/routes/foo") as response:
        assert await response.text() == (
            "NestedRoutes.foo + NestedApp.baz + NestedApp.bar + "
            "RootApp.baz + RootApp.bar"
        )

    async with client.ws_connect("/ping-pong") as ws:
        await ws.send_str("ping")
        msg = await ws.receive_str()
        assert msg == "pong"
        await ws.send_str("close")
