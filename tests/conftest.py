import asyncio
import hashlib
import hmac
import json

import pytest
import redis
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
        marketplace_webhook_secret=b'marketplace_webhook_secret',
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


@pytest.fixture(name='flush_redis')
def fix_flush_redis(settings):
    with redis.from_url(settings.redis_dsn) as redis_client:
        redis_client.flushdb()


@pytest.fixture(name='client')
def fix_client(settings: Settings, loop):
    from src import app

    with Client(app) as client:
        yield client


@pytest.fixture(name='dummy_server')
def _fix_dummy_server(loop, flush_redis):
    from src import github_auth

    loop = asyncio.get_event_loop()
    ctx = {'dynamic': {}}
    ds = loop.run_until_complete(create_dummy_server(loop, extra_routes=routes, extra_context=ctx))
    ctx['dynamic']['github_base_url'] = ds.server_name
    github_auth.github_base_url = ds.server_name

    yield ds

    loop.run_until_complete(ds.stop())


@pytest.fixture(name='webhook')
def fix_webhook(settings: Settings, client: Client):
    def post_webhook(data):
        request_body = json.dumps(data).encode()
        digest = hmac.new(settings.webhook_secret.get_secret_value(), request_body, hashlib.sha256).hexdigest()
        return client.post('/', data=request_body, headers={'x-hub-signature-256': f'sha256={digest}'})

    return post_webhook
