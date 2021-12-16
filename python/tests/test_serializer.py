from datetime import datetime, date

import pytest
from pytz import UTC, timezone

from myack.serializer import Serializable, Serializer


@pytest.mark.asyncio
async def test_serializer(conductor):
    class Foo(Serializable):
        def dump(self):
            return {"foo": "bar"}

    serializer = await conductor(Serializer)

    assert serializer.loads('{"x": 1}') == {"x": 1}
    assert serializer.dumps({"x": 1}) == '{"x":1}'
    assert serializer.dumps(Foo()) == '{"foo":"bar"}'

    assert serializer.loadb(b'{"x": 1}') == {"x": 1}
    assert serializer.dumpb({"x": 1}) == b'{"x":1}'
    assert serializer.dumpb(Foo()) == b'{"foo":"bar"}'

    with pytest.raises(TypeError) as info:
        serializer.dumps(object())
    assert info.value.args == (f"Type {object} is not JSON-serializable",)

    with pytest.raises(TypeError) as info:
        serializer.dumpb(object())
    assert info.value.args == (f"Type {object} is not JSON-serializable",)

    for tz in (timezone("Asia/Tokyo"), timezone("US/Eastern"), UTC):
        dt = datetime.now(tz=UTC).astimezone(tz)
        res = serializer.loads(serializer.dumps(dt))
        assert res == dt
        assert res.utcoffset().total_seconds() == 0

    dt = datetime.now()
    res = serializer.loads(serializer.dumps(dt))
    assert res == dt
    assert res.utcoffset() is None

    d = date.today()
    assert d == serializer.loads(serializer.dumps(d))

    t = datetime.now().time()
    assert t == serializer.loads(serializer.dumps(t))

    mapping = {1: "x", 2: "y"}
    assert mapping == serializer.loads(serializer.dumps(mapping))

    set_ = {1, 2, 3}
    assert set_ == serializer.loads(serializer.dumps(set_))
