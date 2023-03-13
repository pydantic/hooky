from foxglove.test_server import DummyServer

from src.settings import Settings

from .conftest import Client


def test_config_cached(client: Client, settings: Settings, dummy_server: DummyServer):
    data = {
        'comment': {'body': 'Hello world', 'user': {'login': 'user1'}, 'id': 123456},
        'issue': {
            'pull_request': {'url': 'https://api.github.com/repos/user1/repo1/pulls/123'},
            'user': {'login': 'user1'},
            'number': 123,
        },
        'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
    }
    r = client.webhook(data)
    assert r.status_code == 202, r.text
    assert r.text == (
        "[Label and assign] neither 'please update' nor 'please review' found in comment body, no action taken"
    )
    log1 = [
        'GET /repos/user1/repo1/installation > 200',
        'POST /app/installations/654321/access_tokens > 200',
        'GET /repos/user1/repo1 > 200',
        'GET /repos/user1/repo1/pulls/123 > 200',
        'GET /repos/user1/repo1/contents/.hooky.toml?ref=main > 404',
        'GET /repos/user1/repo1/contents/pyproject.toml?ref=main > 200',
        'DELETE /repos/user1/repo1/issues/123/assignees > 200',
    ]
    assert dummy_server.log == log1

    # do it again, installation is cached
    r = client.webhook(data)
    assert r.status_code == 202, r.text
    assert r.text == (
        "[Label and assign] neither 'please update' nor 'please review' found in comment body, no action taken"
    )
    assert dummy_server.log == log1 + ['GET /repos/user1/repo1 > 200', 'GET /repos/user1/repo1/pulls/123 > 200']
