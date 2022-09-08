import hashlib
import hmac

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


def test_issue(webhook):
    r = webhook(
        {
            'comment': {'body': 'Hello world', 'user': {'login': 'user1'}, 'id': 123456},
            'issue': {'user': {'login': 'user1'}, 'number': 123},
            'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
        }
    )
    assert r.status_code == 202, r.text
    assert r.text == 'action only applies to Pull Requests, not Issues, no action taken'


def test_please_review(dummy_server: DummyServer, webhook):
    data = {
        'comment': {'body': 'Hello world, please review', 'user': {'login': 'user1'}, 'id': 123456},
        'issue': {
            'pull_request': {'url': 'https://api.github.com/repos/user1/repo1/pulls/123'},
            'user': {'login': 'user1'},
            'number': 123,
        },
        'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
    }
    r = webhook(data)
    assert r.status_code == 200, r.text
    assert r.text == (
        '[Label and assign] Reviewers "user1", "user2" successfully assigned to PR, "ready for review" label added'
    )
    log1 = [
        'GET /repos/user1/repo1/installation > 200',
        'POST /app/installations/654321/access_tokens > 200',
        'GET /repos/user1/repo1 > 200',
        'GET /repos/user1/repo1/pulls/123 > 200',
        'GET /repos/user1/repo1/issues/comments/123456 > 200',
        'POST /repos/user1/repo1/comments/123456/reactions > 200',
        'POST /repos/user1/repo1/issues/123/labels > 200',
        'GET /repos/user1/repo1/issues/123/labels > 200',
        'POST /repos/user1/repo1/issues/123/assignees > 200',
    ]
    assert dummy_server.log == log1

    # do it again, installation is cached
    r = webhook(data)
    assert r.status_code == 200, r.text
    assert r.text == (
        '[Label and assign] Reviewers "user1", "user2" successfully assigned to PR, "ready for review" label added'
    )
    # this time no extra `.../installation` and `.access_tokens`
    assert dummy_server.log == log1 + log1[2:]


def test_comment_please_update(dummy_server: DummyServer, webhook):
    r = webhook(
        {
            'comment': {'body': 'Hello world, please update', 'user': {'login': 'user1'}, 'id': 123456},
            'issue': {
                'pull_request': {'url': 'https://api.github.com/repos/user1/repo1/pulls/123'},
                'user': {'login': 'user1'},
                'number': 123,
            },
            'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
        }
    )
    assert r.status_code == 200, r.text
    assert r.text == (
        '[Label and assign] Author user1 successfully assigned to PR, "awaiting author revision" label added'
    )
    assert dummy_server.log == [
        'GET /repos/user1/repo1/installation > 200',
        'POST /app/installations/654321/access_tokens > 200',
        'GET /repos/user1/repo1 > 200',
        'GET /repos/user1/repo1/pulls/123 > 200',
        'GET /repos/user1/repo1/issues/comments/123456 > 200',
        'POST /repos/user1/repo1/comments/123456/reactions > 200',
        'POST /repos/user1/repo1/issues/123/labels > 200',
        'GET /repos/user1/repo1/issues/123/labels > 200',
        'POST /repos/user1/repo1/issues/123/assignees > 200',
        'DELETE /repos/user1/repo1/issues/123/assignees > 200',
    ]


def test_review_please_update(dummy_server: DummyServer, webhook):
    r = webhook(
        {
            'review': {'body': 'Hello world', 'user': {'login': 'user1'}, 'state': 'comment'},
            'pull_request': {
                'number': 123,
                'user': {'login': 'user1'},
                'state': 'open',
                'pull_request': 'this is the body',
            },
            'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
        }
    )
    assert r.status_code == 202, r.text
    assert r.text == (
        "[Label and assign] neither 'please update' nor 'please review' found in comment body, no action taken"
    )
    assert dummy_server.log == [
        'GET /repos/user1/repo1/installation > 200',
        'POST /app/installations/654321/access_tokens > 200',
        'GET /repos/user1/repo1 > 200',
        'GET /repos/user1/repo1/pulls/123 > 200',
    ]


def test_review_no_body(dummy_server: DummyServer, webhook):
    r = webhook(
        {
            'review': {'body': None, 'user': {'login': 'user1'}, 'state': 'comment'},
            'pull_request': {
                'number': 123,
                'user': {'login': 'user1'},
                'state': 'open',
                'pull_request': 'this is the body',
            },
            'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
        }
    )
    assert r.status_code == 202, r.text
    assert r.text == '[Label and assign] review has no body, no action taken'
    assert dummy_server.log == []


def test_change_file(dummy_server: DummyServer, webhook):
    r = webhook(
        {
            'action': 'opened',
            'pull_request': {'number': 123, 'user': {'login': 'foobar'}, 'state': 'open', 'body': 'this is a new PR'},
            'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
        }
    )
    assert r.status_code == 200, r.text
    assert r.text == (
        '[Check change file] status set to "success" with description "Change file ID #123 matches the Pull Request"'
    )
    assert dummy_server.log == [
        'GET /repos/user1/repo1/installation > 200',
        'POST /app/installations/654321/access_tokens > 200',
        'GET /repos/user1/repo1 > 200',
        'GET /repos/user1/repo1/pulls/123 > 200',
        'GET /repos/user1/repo1/pulls/123/files > 200',
        'GET /repos/user1/repo1/pulls/123/commits > 200',
        'POST /repos/user1/repo1/statuses/abc > 200',
    ]
