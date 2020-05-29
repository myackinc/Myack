from datetime import date, timedelta

import pytest
import validx

from myack.rpc.api import API, APIVersion, Namespace, handler, middleware
from myack.rpc.request import Request
from myack.rpc.exc import (
    RPCUnsupportedVersion,
    RPCUndefinedMethod,
    RPCInvalidParams,
    RPCInternalError,
    RPCDeprecatedVersion,
)
from myack.exc import BaseError


@pytest.mark.asyncio
async def test_api(conductor):
    retire = date.today() + timedelta(days=90)

    class DivisionByZero(BaseError, code="division_by_zero"):
        message = "Division by zero"

    class Nested(Namespace):
        @handler
        async def get_nothing(self):
            return

    class Foo(Namespace):
        nested: Nested

        @middleware(1)
        async def middleware_1(self, handler, request):
            response = await handler(request)
            response.meta.setdefault("middlewares", []).append("Foo.middleware_1")
            return response

        @middleware(2)
        async def middleware_2(self, handler, request):
            response = await handler(request)
            response.meta.setdefault("middlewares", []).append("Foo.middleware_2")
            return response

        @handler(schema=validx.Dict({"x": validx.Int(), "y": validx.Int()}))
        async def sum(self, x, y, injection=None):
            return x + y, injection

        @handler(schema=validx.Dict({"x": validx.Int(), "y": validx.Int()}))
        async def incorrect_div(self, x, y, injection=None):
            return x / y, injection

        @handler(
            schema=validx.Dict({"x": validx.Int(), "y": validx.Int()}),
            raises=DivisionByZero,
        )
        async def div(self, x, y, injection=None):
            try:
                return x / y, injection
            except ZeroDivisionError:
                raise DivisionByZero()

    class V10(APIVersion, version=(1, 0), retire=retire):

        foo: Foo

        @middleware(1)
        async def middleware_1(self, handler, request):
            response = await handler(request)
            response.meta.setdefault("middlewares", []).append("V10.middleware_1")
            return response

        @middleware(2)
        async def middleware_2(self, handler, request):
            response = await handler(request)
            response.meta.setdefault("middlewares", []).append("V10.middleware_2")
            return response

    class V21(APIVersion, version=(2, 1)):

        foo: Foo

        @middleware(1)
        async def middleware_1(self, handler, request):
            response = await handler(request)
            response.meta.setdefault("middlewares", []).append("V21.middleware_1")
            return response

        @middleware(2)
        async def middleware_2(self, handler, request):
            response = await handler(request)
            response.meta.setdefault("middlewares", []).append("V21.middleware_2")
            return response

    class App(API):
        foo: Foo
        v10: V10
        v21: V21

        @middleware(1)
        async def middleware_1(self, handler, request):
            response = await handler(request)
            response.meta.setdefault("middlewares", []).append("App.middleware_1")
            return response

        @middleware(2)
        async def middleware_2(self, handler, request):
            response = await handler(request)
            response.meta.setdefault("middlewares", []).append("App.middleware_2")
            return response

        @middleware(3)
        async def injector(sefl, handler, request):
            if "injection" in request.handler_signature.parameters:
                request.injections["injection"] = 10
            return await handler(request)

    app = await conductor(App)

    response = await app.dispatch(
        Request(id=1, method="foo.sum", params={"x": 1, "y": 2})
    )
    assert response.result == (3, 10)
    assert response.meta == {
        "middlewares": [
            "Foo.middleware_2",
            "Foo.middleware_1",
            "App.middleware_2",
            "App.middleware_1",
        ]
    }
    assert response.warnings == []
    response = await app.dispatch(Request(id=1, method="foo.nested.get_nothing"))
    assert response.result is None

    response = await app.dispatch(
        Request(
            id=1, method="foo.sum", params={"x": 1, "y": 2}, meta={"version": (1, 0)}
        )
    )
    assert response.result == (3, 10)
    assert response.meta == {
        "version": (1, 0),
        "middlewares": [
            "Foo.middleware_2",
            "Foo.middleware_1",
            "V10.middleware_2",
            "V10.middleware_1",
            "App.middleware_2",
            "App.middleware_1",
        ],
    }
    assert response.warnings == [RPCDeprecatedVersion(retire=retire)]
    response = await app.dispatch(
        Request(id=1, method="foo.nested.get_nothing", meta={"version": (1, 0)})
    )
    assert response.result is None

    response = await app.dispatch(
        Request(
            id=1, method="foo.sum", params={"x": 1, "y": 2}, meta={"version": (2, 0)}
        )
    )
    assert response.result == (3, 10)
    assert response.meta == {
        "version": (2, 1),
        "middlewares": [
            "Foo.middleware_2",
            "Foo.middleware_1",
            "V21.middleware_2",
            "V21.middleware_1",
            "App.middleware_2",
            "App.middleware_1",
        ],
    }
    assert response.warnings == []
    response = await app.dispatch(
        Request(id=1, method="foo.nested.get_nothing", meta={"version": (2, 0)})
    )
    assert response.result is None

    with pytest.raises(RPCUnsupportedVersion) as info:
        await app.dispatch(
            Request(
                id=1,
                method="foo.sum",
                params={"x": 1, "y": 2},
                meta={"version": (3, 0)},
            )
        )
    assert info.value.data["version"] == (3, 0)

    with pytest.raises(RPCUnsupportedVersion) as info:
        await app.dispatch(
            Request(
                id=1,
                method="foo.sum",
                params={"x": 1, "y": 2},
                meta={"version": (2, 2)},
            )
        )
    assert info.value.data == {"version": (2, 2)}

    with pytest.raises(RPCUndefinedMethod) as info:
        await app.dispatch(
            Request(
                id=1,
                method="foo.undefined",
                params={"x": 1, "y": 2},
                meta={"version": (2, 0)},
            )
        )
    assert info.value.data == {"version": (2, 1), "method": "foo.undefined"}

    with pytest.raises(RPCInvalidParams) as info:
        await app.dispatch(
            Request(
                id=1,
                method="foo.sum",
                params={"x": "1", "y": 2},
                meta={"version": (2, 0)},
            )
        )
    assert info.value.data == {
        "version": (2, 1),
        "method": "foo.sum",
        "reason": {"x": "Expected type “int”, got “str”."},
    }

    with pytest.raises(RPCInternalError) as info:
        await app.dispatch(
            Request(
                id=1,
                method="foo.incorrect_div",
                params={"x": 1, "y": 0},
                meta={"version": (2, 0)},
            )
        )
    assert info.value.data == {"version": (2, 1), "method": "foo.incorrect_div"}

    with pytest.raises(DivisionByZero) as info:
        await app.dispatch(
            Request(
                id=1,
                method="foo.div",
                params={"x": 1, "y": 0},
                meta={"version": (2, 0)},
            )
        )
    assert info.value.data == {"version": (2, 1), "method": "foo.div"}

    response = await app.dispatch(Request(id=1, method="list_versions"))
    assert response.result == [
        {"version": (1, 0), "description": "", "deprecated": True, "retire": retire},
        {"version": (2, 1), "description": "", "deprecated": False, "retire": None},
    ]

    response = await app.dispatch(Request(id=1, method="list_exceptions"))
    assert response.result[0] == {
        "code": "error",
        "message": None,
        "description": "Base class of error exceptions",
    }
    response20 = await app.dispatch(
        Request(id=1, method="list_exceptions", meta={"version": (2, 0)})
    )
    assert response20.result == response.result

    response = await app.dispatch(Request(id=1, method="list_methods"))
    assert response.result[0] == {
        "name": "foo.div",
        "raises": ["error.division_by_zero"],
        "schema": {
            "__class__": "Dict",
            "schema": {"x": {"__class__": "Int"}, "y": {"__class__": "Int"}},
        },
        "shield": True,
        "description": "",
    }
    assert response.result[-1] == {
        "name": "list_versions",
        "raises": [],
        "schema": {"__class__": "Dict", "schema": {}},
        "shield": False,
        "builtin": True,
        "description": "List supported API versions",
    }

    response = await app.dispatch(
        Request(id=1, method="list_methods", meta={"version": (2, 0)})
    )
    assert response.result[0] == {
        "name": "foo.div",
        "raises": ["error.division_by_zero"],
        "schema": {
            "__class__": "Dict",
            "schema": {"x": {"__class__": "Int"}, "y": {"__class__": "Int"}},
        },
        "shield": True,
        "description": "",
    }
    assert response.result[-1] == {
        "name": "list_methods",
        "raises": [],
        "schema": {"__class__": "Dict", "schema": {}},
        "shield": False,
        "builtin": True,
        "description": "List methods provided by API/Version",
    }
