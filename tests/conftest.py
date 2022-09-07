import asyncio

import pytest
from foxglove.test_server import create_dummy_server
from foxglove.testing import TestClient

from src.settings import Settings

from .dummy_server import routes


@pytest.fixture(name='settings', scope='session')
def fix_settings():
    return Settings.load_cached(
        github_app_id='12345',
        redis_dsn='redis://localhost:6379/5',
        webhook_secret=b'webhook_secret',
        reviewers=['user1', 'user2'],
        github_app_secret_key='tests/test_github_app_secret_key.pem',
    )


class Client(TestClient):
    """
    Subclass in case we want to extend in future without refactoring
    """


@pytest.fixture(name='loop')
def fix_loop(settings):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


@pytest.fixture(name='client')
def fix_client(settings: Settings, loop):
    from src import app

    with Client(app) as client:
        yield client


@pytest.fixture(name='dummy_server')
def _fix_dummy_server(loop):
    from src import github_auth

    loop = asyncio.get_event_loop()
    ctx = {'dynamic': {}}
    ds = loop.run_until_complete(create_dummy_server(loop, extra_routes=routes, extra_context=ctx))
    ctx['dynamic']['github_base_url'] = ds.server_name
    github_auth.github_base_url = ds.server_name

    yield ds

    loop.run_until_complete(ds.stop())
