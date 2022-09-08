import base64
from dataclasses import dataclass

import pytest
from foxglove.test_server import DummyServer
from github import GithubException

from src.github_auth import get_config
from src.settings import Settings


def test_config_cached(webhook, settings: Settings, dummy_server: DummyServer):
    data = {
        'comment': {'body': 'Hello world', 'user': {'login': 'user1'}, 'id': 123456},
        'issue': {
            'pull_request': {'url': 'https://api.github.com/repos/user1/repo1/pulls/123'},
            'user': {'login': 'user1'},
            'number': 123,
        },
        'repository': {'full_name': 'user1/repo1', 'owner': {'login': 'user1'}},
    }
    r = webhook(data)
    assert r.status_code == 202, r.text
    assert r.text == (
        "[Label and assign] neither 'please update' nor 'please review' found in comment body, no action taken"
    )
    log1 = [
        'GET /repos/user1/repo1/installation > 200',
        'POST /app/installations/654321/access_tokens > 200',
        'GET /repos/user1/repo1 > 200',
        'GET /repos/user1/repo1/contents/pyproject.toml > 200',
        'GET /repos/user1/repo1/pulls/123 > 200',
    ]
    assert dummy_server.log == log1

    # do it again, installation is cached
    r = webhook(data)
    assert r.status_code == 202, r.text
    assert r.text == (
        "[Label and assign] neither 'please update' nor 'please review' found in comment body, no action taken"
    )
    assert dummy_server.log == log1 + ['GET /repos/user1/repo1 > 200', 'GET /repos/user1/repo1/pulls/123 > 200']


@dataclass
class FakeFileContent:
    content: str


class FakeRepo:
    def __init__(self, content: str | None):
        self.content = content

    def get_contents(self, path: str) -> FakeFileContent:
        assert path == 'pyproject.toml'
        if self.content is None:
            raise GithubException(404, 'Not found', {})
        return FakeFileContent(base64.b64encode(self.content.encode()).decode())


@pytest.mark.parametrize(
    'content,log_contains',
    [
        (None, 'No pyproject.toml found, using defaults: 404 "Not found"'),
        ('foobar', 'Invalid pyproject.toml, using defaults'),
        ('x = 4', 'No [tools.hooky] section found, using defaults'),
        ('[tool.hooky]\nreviewers="foobar"', 'Error validating hooky config, using defaults'),
    ],
)
def test_get_config_invalid(content, log_contains, capsys):
    repo = FakeRepo(content)
    assert get_config(repo) is None
    out, err = capsys.readouterr()
    assert log_contains in out


def test_get_config_valid():
    repo = FakeRepo(
        # language=toml
        """\
[tool.hooky]
reviewers = ["foobar", "barfoo"]
request_update_trigger = 'eggs'
request_review_trigger = 'spam'
awaiting_update_label = 'ham'
awaiting_review_label = 'fries'
no_change_file = 'fake'
require_change_file = false
"""
    )
    config = get_config(repo)
    assert config.dict() == {
        'reviewers': ['foobar', 'barfoo'],
        'request_update_trigger': 'eggs',
        'request_review_trigger': 'spam',
        'awaiting_update_label': 'ham',
        'awaiting_review_label': 'fries',
        'no_change_file': 'fake',
        'require_change_file': False,
    }
