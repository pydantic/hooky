import base64
from dataclasses import dataclass

import pytest
from github import GithubException

from src.repo_config import RepoConfig


@dataclass
class FakeFileContent:
    content: str


class FakeRepo:
    def __init__(self, content: str | dict[str, str] | None, full_name: str = 'test_org/test_repo'):
        if isinstance(content, str) or content is None:
            content = {'.hooky.toml:NotSet': content}
        self.content = content
        self.__calls__ = []
        self.full_name = full_name

    def get_contents(self, path: str, ref: str = 'NotSet') -> FakeFileContent:
        content = self.content.get(f'{path}:{ref}')
        if content is None:
            self.__calls__.append(f'{path}:{ref} -> error')
            raise GithubException(404, 'Not found', {})
        else:
            self.__calls__.append(f'{path}:{ref} -> success')
            return FakeFileContent(base64.b64encode(content.encode()).decode())


@pytest.mark.parametrize(
    'content,log_contains',
    [
        (
            None,
            'test_org/test_repo#[default], No ".hooky.toml" or "pyproject.toml" found, using defaults: 404 "Not found"',
        ),
        ('foobar', 'test_org/test_repo#[default]/.hooky.toml, Invalid config file, using defaults'),
        ('x = 4', 'test_org/test_repo#[default]/.hooky.toml, No [tools.hooky] section found, using defaults'),
        (
            '[tool.hooky]\nreviewers="foobar"',
            'test_org/test_repo#[default]/.hooky.toml, Error validating hooky config, using defaults',
        ),
    ],
)
def test_get_config_invalid(content, log_contains, capsys):
    repo = FakeRepo(content)
    assert RepoConfig._load_raw(repo) is None
    out, err = capsys.readouterr()
    assert log_contains in out


# language=toml
valid_config = """\
[tool.hooky]
reviewers = ['foobar', 'barfoo']
request_update_trigger = 'eggs'
request_review_trigger = 'spam'
awaiting_update_label = 'ham'
awaiting_review_label = 'fries'
no_change_file = 'fake'
require_change_file = false
assignees = ['user_a', 'user_b']
unconfirmed_label = 'unconfirmed label'
"""


def test_get_config_valid():
    repo = FakeRepo(valid_config)
    config = RepoConfig._load_raw(repo)
    assert config.model_dump() == {
        'reviewers': ['foobar', 'barfoo'],
        'request_update_trigger': 'eggs',
        'request_review_trigger': 'spam',
        'awaiting_update_label': 'ham',
        'awaiting_review_label': 'fries',
        'no_change_file': 'fake',
        'require_change_file': False,
        'assignees': ['user_a', 'user_b'],
        'unconfirmed_label': 'unconfirmed label',
    }


@dataclass
class FakeBase:
    repo: FakeRepo
    ref: str


@dataclass
class CustomPr:
    base: FakeBase


def test_cached_default(settings, redis_cli, capsys):
    repo = FakeRepo({'pyproject.toml:main': None, 'pyproject.toml:NotSet': valid_config})
    pr = CustomPr(base=FakeBase(repo=repo, ref='main'))
    config = RepoConfig.load(pr=pr, settings=settings)
    assert config.reviewers == ['foobar', 'barfoo']
    assert repo.__calls__ == [
        '.hooky.toml:main -> error',
        'pyproject.toml:main -> error',
        '.hooky.toml:NotSet -> error',
        'pyproject.toml:NotSet -> success',
    ]
    config = RepoConfig.load(pr=pr, settings=settings)
    assert config.reviewers == ['foobar', 'barfoo']
    assert repo.__calls__ == [
        '.hooky.toml:main -> error',
        'pyproject.toml:main -> error',
        '.hooky.toml:NotSet -> error',
        'pyproject.toml:NotSet -> success',
        '.hooky.toml:main -> error',
        'pyproject.toml:main -> error',
    ]
    out, err = capsys.readouterr()
    assert (
        'test_org/test_repo#[default]/pyproject.toml, '
        "config: reviewers=['foobar', 'barfoo'] request_update_trigger='eggs'"
    ) in out
