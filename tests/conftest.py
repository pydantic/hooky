import pytest
from foxglove.testing import TestClient

from src.settings import Settings


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


@pytest.fixture(name='client')
def fix_client(settings: Settings):
    from src import app

    with Client(app) as client:
        yield client
