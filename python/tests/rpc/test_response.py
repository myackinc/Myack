from myack.rpc.response import Response
from myack.exc import BaseError, BaseWarning


def test_dump():
    response = Response(result="foo")
    assert response.dump() == {
        "id": None,
        "meta": {},
        "result": "foo",
        "error": None,
        "warnings": [],
    }

    response = Response(1, result="foo")
    assert response.dump() == {
        "id": 1,
        "meta": {},
        "result": "foo",
        "error": None,
        "warnings": [],
    }

    response = Response(1, meta={"foo": "bar"}, result="foo")
    assert response.dump() == {
        "id": 1,
        "meta": {"foo": "bar"},
        "result": "foo",
        "error": None,
        "warnings": [],
    }

    error = BaseError("Something went wrong")
    response = Response(1, error=error)
    assert response.dump() == {
        "id": 1,
        "meta": {},
        "result": None,
        "error": error,
        "warnings": [],
    }

    warning = BaseWarning("Deprecated")
    response.warnings.append(warning)
    assert response.dump() == {
        "id": 1,
        "meta": {},
        "result": None,
        "error": error,
        "warnings": [warning],
    }
