from myack import exc


def test_exc():
    class TestError(exc.BaseError, code="test"):
        message: str = "Test error"

    class NestedTestError(TestError, code="nested"):
        message: str = "Nested test error"

    assert TestError.code == "error.test"
    assert NestedTestError.code == "error.test.nested"

    e = exc.BaseExc.dispatch("error.test")
    assert isinstance(e, TestError)
    assert e.code == "error.test"
    assert e.message == "Test error"
    assert e.data == {}

    e = exc.BaseExc.dispatch("error.test", "Custom error message")
    assert isinstance(e, TestError)
    assert e.code == "error.test"
    assert e.message == "Custom error message"
    assert e.data == {}

    e = exc.BaseExc.dispatch("error.test", foo="bar")
    assert isinstance(e, TestError)
    assert e.code == "error.test"
    assert e.message == "Test error"
    assert e.data == {"foo": "bar"}

    e = exc.BaseExc.dispatch("invalid", "Other error", foo="bar")
    assert isinstance(e, exc.UndefinedExc)
    assert e.code == "undefined"
    assert e.message == "Undefined exception"
    assert e.data == {
        "original": {
            "code": "invalid",
            "message": "Other error",
            "data": {"foo": "bar"},
        }
    }

    e = TestError()
    assert e.dump() == {"code": "error.test", "message": "Test error", "data": {}}

    e = TestError("Custom error message")
    assert e.dump() == {
        "code": "error.test",
        "message": "Custom error message",
        "data": {},
    }

    e = TestError(foo="bar")
    assert e.dump() == {
        "code": "error.test",
        "message": "Test error",
        "data": {"foo": "bar"},
    }

    assert TestError(foo="bar") == TestError(foo="bar")
    assert TestError(foo="bar") != TestError(bar="baz")
