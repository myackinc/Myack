import pytest

from myack.rpc.request import Request
from myack.rpc.exc import RPCInvalidRequest


def test_load():
    request = Request.load({"id": 1, "method": "foo"})
    assert request.id == 1
    assert request.method == "foo"
    assert request.meta == {}
    assert request.params == {}
    assert request.injections == {}
    assert request.handler_info == {}

    request = Request.load(
        {"id": 1, "method": "foo", "meta": {"x": "y"}, "params": {"a": "b"}}
    )
    assert request.id == 1
    assert request.method == "foo"
    assert request.meta == {"x": "y"}
    assert request.params == {"a": "b"}
    assert request.injections == {}
    assert request.handler_info == {}

    request = Request.load(
        {
            "id": 1,
            "method": "foo",
            "meta": {"version": [1, 0], "access_token": "xyz", "x": "y"},
            "params": {"a": "b"},
        }
    )
    assert request.id == 1
    assert request.method == "foo"
    assert request.meta == {"version": (1, 0), "access_token": "xyz", "x": "y"}
    assert request.params == {"a": "b"}
    assert request.injections == {}
    assert request.handler_info == {}

    with pytest.raises(RPCInvalidRequest) as info:
        Request.load({"id": None, "method": "foo"})
    assert info.value.data == {"reason": {"id": "Value should not be null."}}


def test_handler():
    async def foo(x: int, y: int):
        pass

    request = Request.load({"id": 1, "method": "foo", "params": {"x": 1, "y": 1}})
    request.handler = foo

    assert "x" in request.handler_signature.parameters
    assert "y" in request.handler_signature.parameters
    assert "z" not in request.handler_signature.parameters


def test_response():
    request = Request.load({"id": 1, "method": "foo"})
    response = request.response(result="bar", meta={"foo": "bar"})
    assert response.id == 1
    assert response.meta == {"foo": "bar"}
    assert response.result == "bar"
