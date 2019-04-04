import pytest
from aioconductor import Conductor
from configtree import Tree

from myack import exc


@pytest.fixture
def conductor(event_loop):
    async def sigleton(*components, config=None):
        assert sigleton.instance is None
        sigleton.instance = instance = Conductor(
            config=config or Tree(), loop=event_loop
        )
        result = [instance.add(component) for component in components]
        await instance.setup()
        return result[0] if len(result) == 1 else result

    sigleton.instance = None
    yield sigleton

    if sigleton.instance is not None:
        event_loop.run_until_complete(sigleton.instance.shutdown())


@pytest.fixture(autouse=True)
def exc_registry():
    backup = dict(exc.BaseExc.registry)
    yield exc.BaseExc.registry
    exc.BaseExc.registry = backup
