from time import time
from datetime import datetime, timedelta

import pytest
from pytz import UTC, timezone

from myack.timer import Timer


@pytest.mark.asyncio
async def test_timer(conductor):
    timer = await conductor(Timer)

    def cmpts(left, right):
        return left <= right <= left + 0.001

    def cmpdt(left, right):
        return left <= right <= left + timedelta(milliseconds=1)

    assert not timer.shifted

    dtnow = datetime.now(UTC)
    tsnow = time()
    assert cmpdt(dtnow, timer.dtnow())
    assert cmpts(tsnow, timer.tsnow())

    timer.goto(2019, 1, 8, 19, 35)
    assert timer.shifted

    dtnow = datetime(2019, 1, 8, 19, 35, tzinfo=UTC)
    tsnow = dtnow.timestamp()
    assert cmpdt(dtnow, timer.dtnow())
    assert cmpts(tsnow, timer.tsnow())

    timer.reset()
    assert not timer.shifted
    assert not cmpdt(dtnow, timer.dtnow())
    assert not cmpts(tsnow, timer.tsnow())

    dtnow = datetime(2019, 1, 8, 19, 35, tzinfo=UTC).astimezone(timezone("US/Eastern"))
    tsnow = dtnow.timestamp()
    timer.goto(dt=dtnow)
    assert timer.shifted
    assert cmpdt(dtnow, timer.dtnow())
    assert cmpts(tsnow, timer.tsnow())

    timer.reset()
    timer.shift(timedelta(minutes=5))
    assert timer.shifted

    dtnow = datetime.now(UTC) + timedelta(minutes=5)
    tsnow = dtnow.timestamp()
    assert cmpdt(dtnow, timer.dtnow())
    assert cmpts(tsnow, timer.tsnow())

    timer.shift(minutes=-10)

    dtnow += timedelta(minutes=-10)
    tsnow -= 10 * 60
    assert cmpdt(dtnow, timer.dtnow())
    assert cmpts(tsnow, timer.tsnow())
