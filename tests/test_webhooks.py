import hashlib
import hmac
import json

from foxglove.test_server import DummyServer

from src.settings import Settings

from .conftest import Client


def test_auth_ok_no_data(client: Client, settings: Settings):
    request_body = b'{}'
    digest = hmac.new(settings.webhook_secret.get_secret_value(), request_body, hashlib.sha256).hexdigest()
    r = client.post('/', data=request_body, headers={'x-hub-signature-256': f'sha256={digest}'})
    assert r.status_code == 202, r.text
    assert r.text == 'Error parsing request body, no action taken'


def test_auth_fails_no_header(client: Client, settings: Settings):
    request_body = b'{}'
    r = client.post('/', data=request_body)
    assert r.status_code == 403, r.text
    assert r.json() == {'detail': 'Invalid signature'}


def test_auth_fails_wrong_header(client: Client, settings: Settings):
    request_body = b'{}'
    r = client.post('/', data=request_body, headers={'x-hub-signature-256': 'sha256=foobar'})
    assert r.status_code == 403, r.text
    assert r.json() == {'detail': 'Invalid signature'}


def test_issue(client: Client, settings: Settings):
    data = {
        'comment': {'body': 'Hello world', 'user': {'login': 'user1'}, 'id': 123456},
        'issue': {'user': {'login': 'user1'}, 'number': 123},
        'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
    }
    request_body = json.dumps(data).encode()
    digest = hmac.new(settings.webhook_secret.get_secret_value(), request_body, hashlib.sha256).hexdigest()
    r = client.post('/', data=request_body, headers={'x-hub-signature-256': f'sha256={digest}'})
    assert r.status_code == 202, r.text
    assert r.text == 'action only applies to Pull Requests, not Issues, no action taken'


def test_please_review(client: Client, settings: Settings, dummy_server: DummyServer):
    data = {
        'comment': {'body': 'Hello world, please review', 'user': {'login': 'user1'}, 'id': 123456},
        'issue': {
            'pull_request': {'url': 'https://api.github.com/repos/user1/repo1/pulls/123'},
            'user': {'login': 'user1'},
            'number': 123,
        },
        'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
    }
    request_body = json.dumps(data).encode()
    digest = hmac.new(settings.webhook_secret.get_secret_value(), request_body, hashlib.sha256).hexdigest()
    r = client.post('/', data=request_body, headers={'x-hub-signature-256': f'sha256={digest}'})
    assert r.status_code == 200, r.text
    assert r.text == (
        '[Label and assign] Reviewers "user1", "user2" successfully assigned to PR, "ready for review" label added'
    )
    assert dummy_server.log == [
        'GET /repos/user1/repo1 > 200',
        'GET /repos/foo/bar/pulls/123 > 200',
        'GET /repos/foo/bar/comments/123456 > 200',
        'POST /repos/foo/bar/comments/123456/reactions > 200',
        'POST /repos/foo/bar/issues/labels > 200',
        'GET /repos/foo/bar/issues/labels > 200',
        'POST /repos/foo/bar/issues/assignees > 200',
    ]
