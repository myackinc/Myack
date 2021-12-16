import typing as t
from concurrent import futures
from functools import partial

from aioconductor import Component


class Executor(Component):

    executor_class: t.ClassVar[t.Type[futures.Executor]]
    instance: futures.Executor

    async def on_setup(self) -> None:
        self.instance = self.executor_class()

    async def on_shutdown(self) -> None:
        self.instance.shutdown()
        del self.instance

    async def run(self, func: t.Callable, *agrs, **kw) -> t.Any:
        return await self.loop.run_in_executor(
            executor=self.instance, func=partial(func, *agrs, **kw)
        )


class IOExecutor(Executor):
    executor_class: t.ClassVar[t.Type[futures.Executor]] = futures.ThreadPoolExecutor
    instance: futures.ThreadPoolExecutor


class CPUExecutor(Executor):
    executor_class: t.ClassVar[t.Type[futures.Executor]] = futures.ProcessPoolExecutor
    instance: futures.ProcessPoolExecutor
