import typing as t
from abc import ABC, abstractmethod
from datetime import datetime, date, time, timedelta, timezone

from aioconductor import Component
import rapidjson


class Serializable(ABC):
    @abstractmethod
    def dump(self) -> t.Any:
        """Dump object into serializable one"""


class Serializer(Component):

    _loads: t.ClassVar[t.Callable] = rapidjson.loads
    _dumps: t.ClassVar[t.Callable] = rapidjson.dumps

    loaders: t.ClassVar[t.Dict[str, t.Callable]] = {}
    dumpers: t.ClassVar[t.Dict[t.Type, t.Callable]] = {}

    @classmethod
    def add_loader(cls, name: str):
        def decorator(func):
            cls.loaders[name] = func
            return func

        return decorator

    @classmethod
    def add_dumper(cls, type_: t.Type, typename: str):
        def decorator(func):
            cls.dumpers[type_] = (typename, func)
            return func

        return decorator

    def dumps(self, data: t.Any) -> str:
        return self._dumps(data, default=self.before_dump)

    def dumpb(self, data: t.Any) -> bytes:
        return self._dumps(data, default=self.before_dump).encode("utf-8")

    def loads(self, data: str) -> t.Any:
        return self._loads(data, object_hook=self.after_load)

    def loadb(self, data: bytes) -> t.Any:
        return self._loads(data, object_hook=self.after_load)

    def before_dump(self, obj):
        if isinstance(obj, Serializable):
            return obj.dump()
        for type_, (typename, dumper) in self.dumpers.items():
            if isinstance(obj, type_):
                return dict(dumper(obj), _type=typename)
        raise TypeError(f"Type {type(obj)} is not JSON-serializable")

    def after_load(self, obj):
        try:
            type_ = obj["_type"]
            loader = self.loaders[type_]
        except KeyError:
            return obj
        del obj["_type"]
        return loader(**obj)


@Serializer.add_dumper(datetime, "datetime")
def dump_datetime(dt):
    utcoffset = dt.utcoffset()
    if utcoffset is not None:
        utcoffset = utcoffset.total_seconds() / 60
    return {
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "hour": dt.hour,
        "minute": dt.minute,
        "second": dt.second,
        "microsecond": dt.microsecond,
        "utcoffset": utcoffset,
    }


@Serializer.add_loader("datetime")
def load_datetime(
    year, month, day, hour=0, minute=0, second=0, microsecond=0, utcoffset=None
):
    if utcoffset is not None:
        # Return TZ-aware datetime in UTC timezone with appropriate offset
        dt = datetime(
            year, month, day, hour, minute, second, microsecond, tzinfo=timezone.utc
        )
        return dt - timedelta(minutes=utcoffset)
    else:
        # Return TZ-naive datetime
        return datetime(year, month, day, hour, minute, second, microsecond)


@Serializer.add_dumper(date, "date")
def dump_date(d):
    return {"year": d.year, "month": d.month, "day": d.day}


@Serializer.add_loader("date")
def load_date(year, month, day):
    return date(year, month, day)


@Serializer.add_dumper(time, "time")
def dump_time(t):
    return {
        "hour": t.hour,
        "minute": t.minute,
        "second": t.second,
        "microsecond": t.microsecond,
    }


@Serializer.add_loader("time")
def load_time(hour=0, minute=0, second=0, microsecond=0):
    return time(hour, minute, second, microsecond)
