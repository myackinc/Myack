import pytest

from myack.executors import IOExecutor, CPUExecutor


def fact(n: int) -> int:
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


@pytest.mark.asyncio
async def test_executors(conductor):
    io, cpu = await conductor(IOExecutor, CPUExecutor)

    assert await io.run(fact, 10) == 3628800
    assert await cpu.run(fact, 10) == 3628800
