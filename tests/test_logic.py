import base64
import re
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from github import GithubException

from src.logic import (
    Comment,
    LabelAssign,
    PullRequest,
    PullRequestUpdateEvent,
    Repository,
    User,
    check_change_file,
    check_change_file_content,
    find_change_file,
)
from src.repo_config import RepoConfig

from .conftest import Magic


def test_assign_author(settings):
    gh_repo = Magic()
    gh_pr = Magic()
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='user1'), id=123456),
        'user1',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    assert la.assign_author() == (
        True,
        'Author user1 successfully assigned to PR, "awaiting author revision" label added',
    )
    assert gh_pr.__history__ == {
        'get_issue_comment': {'args': (123456,), 'return': {'create_reaction': {'args': ('+1',)}}},
        'add_to_labels': {'args': ('awaiting author revision',)},
        'get_labels': {'return': {'__iter__': {'return': []}}},
        'add_to_assignees': {'args': ('user1',)},
        'remove_from_assignees': {'args': ('user2',)},
    }


def test_assign_author_remove_label(settings):
    gh_repo = Magic()
    gh_pr = Magic(get_labels=Magic(__iter__=[Magic(name='ready for review')]))
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='user1'), id=123456),
        'user1',
        RepoConfig(reviewers=['user1']),
        settings,
    )
    assert la.assign_author() == (
        True,
        'Author user1 successfully assigned to PR, "awaiting author revision" label added',
    )
    assert gh_pr.__history__ == {
        'get_issue_comment': {'args': (123456,), 'return': {'create_reaction': {'args': ('+1',)}}},
        'add_to_labels': {'args': ('awaiting author revision',)},
        'get_labels': {
            'return': {'__call__': {'return': {'__iter__': {'return': [{'name': {'return': 'ready for review'}}]}}}}
        },
        'remove_from_labels': {'args': ('ready for review',)},
        'add_to_assignees': {'args': ('user1',)},
    }


def test_request_review(settings):
    gh_repo = Magic()
    gh_pr = Magic()
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='user1'), id=123456),
        'other',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    acted, msg = la.request_review()
    assert acted
    assert msg == 'Reviewers "user1", "user2" successfully assigned to PR, "ready for review" label added'
    assert gh_pr.__history__ == {
        'get_issue_comment': {'args': (123456,), 'return': {'create_reaction': {'args': ('+1',)}}},
        'add_to_labels': {'args': ('ready for review',)},
        'get_labels': {'return': {'__iter__': {'return': []}}},
        'add_to_assignees': {'args': ('user1', 'user2')},
        'remove_from_assignees': {'args': ('other',)},
    }


def test_request_review_from_review(settings):
    gh_repo = Magic()
    gh_pr = Magic()
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'review',
        Comment(body='x', user=User(login='other'), id=123456),
        'other',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    acted, msg = la.request_review()
    assert acted
    assert msg == 'Reviewers "user1", "user2" successfully assigned to PR, "ready for review" label added'
    assert gh_pr.__history__ == {
        'add_to_labels': {'args': ('ready for review',)},
        'get_labels': {'return': {'__iter__': {'return': []}}},
        'add_to_assignees': {'args': ('user1', 'user2')},
        'remove_from_assignees': {'args': ('other',)},
    }


def test_request_review_not_author(settings):
    gh_repo = Magic()
    gh_pr = Magic()
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='commenter'), id=123456),
        'the_auth',
        RepoConfig(),
        settings,
    )
    acted, msg = la.request_review()
    assert not acted
    assert msg == 'Only the PR author the_auth or reviewers can request a review, not commenter'


def test_assign_author_not_reviewer(settings):
    gh_repo = Magic()
    gh_pr = Magic()
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='other'), id=123456),
        'user1',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    assert la.assign_author() == (False, 'Only reviewers "user1", "user2" can assign the author, not other')
    assert gh_pr.__history__ == {}


def test_assign_author_no_reviewers(settings):
    gh_repo = Magic()
    gh_pr = Magic()
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='other'), id=123456),
        'user1',
        RepoConfig(),
        settings,
    )
    assert la.assign_author() == (False, 'Only reviewers (no reviewers configured) can assign the author, not other')
    assert gh_pr.__history__ == {}


def test_change_not_open(settings):
    e = PullRequestUpdateEvent(
        action='foo',
        pull_request=PullRequest(number=123, state='closed', user=User(login='user1'), body=None),
        repository=Repository(full_name='user/repo', owner=User(login='user1')),
    )
    assert check_change_file(e, settings) == (False, '[Check change file] Pull Request is closed, not open')


def test_change_wrong_action(settings):
    e = PullRequestUpdateEvent(
        action='foo',
        pull_request=PullRequest(number=123, state='open', user=User(login='user1'), body=None),
        repository=Repository(full_name='user/repo', owner=User(login='user1')),
    )
    assert check_change_file(e, settings) == (False, '[Check change file] file change not checked on "foo"')


def test_change_user_bot(settings):
    e = PullRequestUpdateEvent(
        action='opened',
        pull_request=PullRequest(number=123, state='open', user=User(login='foobar[bot]'), body=None),
        repository=Repository(full_name='user/repo', owner=User(login='user1')),
    )
    assert check_change_file(e, settings) == (False, '[Check change file] Pull Request author is a bot')


def test_change_no_change_comment(settings, mocker):
    e = PullRequestUpdateEvent(
        action='opened',
        pull_request=PullRequest(number=123, state='open', user=User(login='foobar'), body='skip change file check'),
        repository=Repository(full_name='user/repo', owner=User(login='user1')),
    )
    gh = Magic(
        _requester=Magic(_Requester__connection=Magic(session=Magic())),
        get_pull=Magic(
            get_commits=Magic(__iter__=[None, Magic()]),
            base=Magic(repo=Magic(get_contents=MagicMock(side_effect=GithubException(404, 'Not Found', {})))),
        ),
    )
    mocker.patch('src.logic.get_repo_client', return_value=FakeGhContext(gh))
    assert check_change_file(e, settings) == (
        True,
        (
            '[Check change file] status set to "success" with description '
            '"Found "skip change file check" in Pull Request body"'
        ),
    )


class FakeGhContext:
    def __init__(self, gh):
        self.gh = gh

    def __enter__(self):
        return self.gh

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def test_change_no_change_file(settings, mocker):
    e = PullRequestUpdateEvent(
        action='opened',
        pull_request=PullRequest(number=123, state='open', user=User(login='foobar'), body=None),
        repository=Repository(full_name='user/repo', owner=User(login='user1')),
    )
    gh = Magic(
        _requester=Magic(_Requester__connection=Magic(session=Magic())),
        get_pull=Magic(
            get_commits=Magic(__iter__=[None, Magic()]),
            base=Magic(repo=Magic(get_contents=MagicMock(side_effect=GithubException(404, 'Not Found', {})))),
        ),
    )
    mocker.patch('src.logic.get_repo_client', return_value=FakeGhContext(gh))
    assert check_change_file(e, settings) == (
        True,
        '[Check change file] status set to "error" with description "No change file found"',
    )
    # debug(gh.__history__)


def test_change_file_not_required(settings, mocker):
    e = PullRequestUpdateEvent(
        action='opened',
        pull_request=PullRequest(number=123, state='open', user=User(login='foobar'), body=None),
        repository=Repository(full_name='user/repo', owner=User(login='user1')),
    )
    config_change_not_required = base64.b64encode(b'[tool.hooky]\nrequire_change_file = false').decode()
    gh = Magic(
        _requester=Magic(_Requester__connection=Magic(session=Magic())),
        get_pull=Magic(
            get_commits=Magic(__iter__=[None, Magic()]),
            base=Magic(repo=Magic(get_contents=Magic(content=config_change_not_required))),
        ),
    )
    mocker.patch('src.logic.get_repo_client', return_value=FakeGhContext(gh))
    assert check_change_file(e, settings) == (False, '[Check change file] change file not required')


def test_file_content_match_pr():
    m = re.fullmatch(r'changes/(\d+)-(.+).md', 'changes/123-foobar.md')
    pr = PullRequest(number=123, state='open', user=User(login='foobar'), body=None)
    status, msg = check_change_file_content(m, 'nothing', pr)
    assert status == 'success'
    assert msg == 'Change file ID #123 matches the Pull Request'


def test_file_content_match_issue():
    m = re.fullmatch(r'changes/(\d+)-(.+).md', 'changes/42-foobar.md')
    pr = PullRequest(number=123, state='open', user=User(login='foobar'), body=None)
    status, msg = check_change_file_content(m, 'fix #42', pr)
    assert status == 'success'
    assert msg == 'Change file ID #42 matches Issue closed by the Pull Request'


def test_file_content_match_issue_url():
    m = re.fullmatch(r'changes/(\d+)-(.+).md', 'changes/42-foobar.md')
    pr = PullRequest(number=123, state='open', user=User(login='foobar'), body=None)
    status, msg = check_change_file_content(m, 'closes https://github.com/foo/bar/issues/42', pr)
    assert status == 'success'
    assert msg == 'Change file ID #42 matches Issue closed by the Pull Request'


def test_file_content_error():
    m = re.fullmatch(r'changes/(\d+)-(.+).md', 'changes/42-foobar.md')
    pr = PullRequest(number=123, state='open', user=User(login='foobar'), body=None)
    status, msg = check_change_file_content(m, '', pr)
    assert status == 'error'
    assert msg == 'Change file ID does not match Pull Request or closed Issue'


def test_file_content_wrong_author():
    m = re.fullmatch(r'changes/(\d+)-(.+).md', 'changes/123-foobar.md')
    pr = PullRequest(number=123, state='open', user=User(login='another'), body=None)
    status, msg = check_change_file_content(m, 'nothing', pr)
    assert status == 'error'
    assert msg == 'File "changes/123-foobar.md" has wrong author, expected "another"'


@dataclass
class FakeFile:
    status: str
    filename: str


@dataclass
class FakePr:
    _files: list[FakeFile]

    def get_files(self):
        return self._files


@pytest.mark.parametrize(
    'files,expected',
    [
        ([], None),
        ([FakeFile('added', 'changes/123-foobar.md')], ('123', 'foobar')),
        ([FakeFile('added', 'foobar'), FakeFile('added', 'changes/123-foobar.md')], ('123', 'foobar')),
        ([FakeFile('added', 'foobar'), FakeFile('removed', 'changes/123-foobar.md')], None),
    ],
    ids=repr,
)
def test_find_change_file_ok(files, expected):
    m = find_change_file(FakePr(files))
    if expected is None:
        assert m is None
    else:
        assert m.groups() == expected
