import typing as t
from time import time
from datetime import datetime, timedelta, tzinfo, timezone

from aioconductor import Component


class Timer(Component):

    _current: t.Optional[float]
    _updated: t.Optional[float]

    async def on_setup(self) -> None:
        self.reset()

    def dtnow(self, tz: tzinfo = timezone.utc) -> datetime:
        now = datetime.fromtimestamp(self.tsnow(), tz=timezone.utc)
        return now if tz is timezone.utc else now.astimezone(tz)

    def tsnow(self) -> float:
        now = time()
        if self._current is None or self._updated is None:
            return now
        return self._current + now - self._updated

    @property
    def shifted(self):
        return self._updated is not None

    def reset(self) -> None:
        self._current = None
        self._updated = None

    def goto(
        self,
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
        *,
        dt: datetime = None,
    ) -> None:
        if dt is None:
            assert year is not None and month is not None and day is not None
            dt = datetime(
                year, month, day, hour, minute, second, microsecond, timezone.utc
            )
        self._current = dt.timestamp()
        self._updated = time()

    def shift(
        self,
        td: timedelta = None,
        *,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        milliseconds: int = 0,
        microseconds: int = 0,
    ) -> None:
        self._updated = time()
        if td is None:
            td = timedelta(
                weeks=weeks,
                days=days,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
                milliseconds=milliseconds,
                microseconds=microseconds,
            )
        if self._current is None:
            self._current = self._updated
        self._current += td.total_seconds()
