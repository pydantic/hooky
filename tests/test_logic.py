import base64
import re
from dataclasses import dataclass

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

from .blocks import AttrBlock, CallableBlock, IterBlock


@pytest.fixture(name='gh_repo')
def fix_gh_repo():
    return AttrBlock('GhRepo', get_collaborators=CallableBlock('get_collaborators', IterBlock('collaborators')))


@pytest.fixture(name='gh_pr')
def fix_gh_pr():
    return AttrBlock(
        'GhPr',
        get_issue_comment=CallableBlock(
            'get_issue_comment', AttrBlock('Comment', create_reaction=CallableBlock('create_reaction'))
        ),
        body='this is the pr body',
        add_to_labels=CallableBlock('add_to_labels'),
        get_labels=CallableBlock('get_labels', IterBlock('get_labels', AttrBlock('labels', name='ready for review'))),
        remove_from_labels=CallableBlock('remove_from_labels'),
        add_to_assignees=CallableBlock('add_to_assignees'),
        remove_from_assignees=CallableBlock('remove_from_assignees'),
        edit=CallableBlock('edit'),
    )


def test_assign_author(settings, gh_pr, gh_repo):
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='user1'), id=123456),
        'user1',
        'org/repo',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    assert la.assign_author() == (
        True,
        'Author user1 successfully assigned to PR, "awaiting author revision" label added',
    )
    # insert_assert(gh_pr.__history__)
    assert gh_pr.__history__ == [
        "get_issue_comment: Call(123456) -> AttrBlock('Comment', create_reaction=CallableBlock('create_reaction'))",
        "get_issue_comment.create_reaction: Call('+1')",
        "add_to_labels: Call('awaiting author revision')",
        "get_labels: Call() -> IterBlock('get_labels', AttrBlock('labels', name='ready for review'))",
        "get_labels: Iter(AttrBlock('labels', name='ready for review'))",
        "remove_from_labels: Call('ready for review')",
        "add_to_assignees: Call('user1')",
        "remove_from_assignees: Call('user2')",
    ]


def test_assign_author_remove_label(settings, gh_pr, gh_repo):
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='user1'), id=123456),
        'user1',
        'org/repo',
        RepoConfig(reviewers=['user1']),
        settings,
    )
    assert la.assign_author() == (
        True,
        'Author user1 successfully assigned to PR, "awaiting author revision" label added',
    )
    # insert_assert(gh_pr.__history__)
    assert gh_pr.__history__ == [
        "get_issue_comment: Call(123456) -> AttrBlock('Comment', create_reaction=CallableBlock('create_reaction'))",
        "get_issue_comment.create_reaction: Call('+1')",
        "add_to_labels: Call('awaiting author revision')",
        "get_labels: Call() -> IterBlock('get_labels', AttrBlock('labels', name='ready for review'))",
        "get_labels: Iter(AttrBlock('labels', name='ready for review'))",
        "remove_from_labels: Call('ready for review')",
        "add_to_assignees: Call('user1')",
    ]


def test_author_request_review(settings, gh_pr, gh_repo, flush_redis):
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='the_author'), id=123456),
        'the_author',
        'org/repo',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    acted, msg = la.request_review()
    assert acted, msg
    assert msg == '@user1 successfully assigned to PR as reviewer, "ready for review" label added'
    # insert_assert(gh_pr.__history__)
    assert gh_pr.__history__ == [
        "get_issue_comment: Call(123456) -> AttrBlock('Comment', create_reaction=CallableBlock('create_reaction'))",
        "get_issue_comment.create_reaction: Call('+1')",
        "add_to_labels: Call('ready for review')",
        "get_labels: Call() -> IterBlock('get_labels', AttrBlock('labels', name='ready for review'))",
        "get_labels: Iter(AttrBlock('labels', name='ready for review'))",
        "edit: Call(body='this is the pr body\\n\\nSelected Reviewer: @user1')",
        "remove_from_assignees: Call('the_author')",
        "add_to_assignees: Call('user1')",
    ]

    la2 = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='author2'), id=123456),
        'author2',
        'org/repo',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    acted, msg = la2.request_review()
    assert acted
    assert msg == '@user2 successfully assigned to PR as reviewer, "ready for review" label added'


def test_request_review_magic_comment(settings, gh_repo, flush_redis):
    gh_pr = AttrBlock(
        'GhPr',
        get_issue_comment=CallableBlock(
            'get_issue_comment', AttrBlock('Comment', create_reaction=CallableBlock('create_reaction'))
        ),
        body='this is the pr body\n\nSelected Reviewer: @user2',
        add_to_labels=CallableBlock('add_to_labels'),
        get_labels=CallableBlock('get_labels', IterBlock('get_labels', AttrBlock('labels', name='ready for review'))),
        remove_from_labels=CallableBlock('remove_from_labels'),
        add_to_assignees=CallableBlock('add_to_assignees'),
        remove_from_assignees=CallableBlock('remove_from_assignees'),
        edit=CallableBlock('edit'),
    )
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='the_author'), id=123456),
        'the_author',
        'org/repo',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    acted, msg = la.request_review()
    assert acted, msg
    assert msg == '@user2 successfully assigned to PR as reviewer, "ready for review" label added'
    # insert_assert(gh_pr.__history__)
    assert gh_pr.__history__ == [
        "get_issue_comment: Call(123456) -> AttrBlock('Comment', create_reaction=CallableBlock('create_reaction'))",
        "get_issue_comment.create_reaction: Call('+1')",
        "add_to_labels: Call('ready for review')",
        "get_labels: Call() -> IterBlock('get_labels', AttrBlock('labels', name='ready for review'))",
        "get_labels: Iter(AttrBlock('labels', name='ready for review'))",
        "remove_from_assignees: Call('the_author')",
        "add_to_assignees: Call('user2')",
    ]


def test_request_review_bad_magic_comment(settings, gh_repo, flush_redis):
    gh_pr = AttrBlock(
        'GhPr',
        get_issue_comment=CallableBlock(
            'get_issue_comment', AttrBlock('Comment', create_reaction=CallableBlock('create_reaction'))
        ),
        body='this is the pr body\n\nSelected Reviewer: @other-person',
        add_to_labels=CallableBlock('add_to_labels'),
        get_labels=CallableBlock('get_labels', IterBlock('get_labels', AttrBlock('labels', name='ready for review'))),
        remove_from_labels=CallableBlock('remove_from_labels'),
        add_to_assignees=CallableBlock('add_to_assignees'),
        remove_from_assignees=CallableBlock('remove_from_assignees'),
        edit=CallableBlock('edit'),
    )
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='the_author'), id=123456),
        'the_author',
        'org/repo',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    acted, msg = la.request_review()
    assert not acted, msg
    assert msg == 'Selected reviewer @other-person not in reviewers.'


def test_request_review_one_reviewer(settings, gh_pr, gh_repo, flush_redis):
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='user1'), id=123456),
        'user1',
        'org/repo',
        RepoConfig(reviewers=['user1']),
        settings,
    )
    acted, msg = la.request_review()
    assert acted, msg
    assert msg == '@user1 successfully assigned to PR as reviewer, "ready for review" label added'
    # insert_assert(gh_pr.__history__)
    assert gh_pr.__history__ == [
        "get_issue_comment: Call(123456) -> AttrBlock('Comment', create_reaction=CallableBlock('create_reaction'))",
        "get_issue_comment.create_reaction: Call('+1')",
        "add_to_labels: Call('ready for review')",
        "get_labels: Call() -> IterBlock('get_labels', AttrBlock('labels', name='ready for review'))",
        "get_labels: Iter(AttrBlock('labels', name='ready for review'))",
        "edit: Call(body='this is the pr body\\n\\nSelected Reviewer: @user1')",
    ]


def test_request_review_from_review(settings, gh_pr, gh_repo, flush_redis):
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'review',
        Comment(body='x', user=User(login='other'), id=123456),
        'other',
        'org/repo',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    acted, msg = la.request_review()
    assert acted
    assert msg == '@user1 successfully assigned to PR as reviewer, "ready for review" label added'
    assert gh_pr.__history__ == [
        "add_to_labels: Call('ready for review')",
        "get_labels: Call() -> IterBlock('get_labels', AttrBlock('labels', name='ready for review'))",
        "get_labels: Iter(AttrBlock('labels', name='ready for review'))",
        "edit: Call(body='this is the pr body\\n\\nSelected Reviewer: @user1')",
        "remove_from_assignees: Call('other')",
        "add_to_assignees: Call('user1')",
    ]


def test_request_review_not_author(settings, gh_pr, gh_repo):
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='commenter'), id=123456),
        'the_auth',
        'org/repo',
        RepoConfig(),
        settings,
    )
    acted, msg = la.request_review()
    assert not acted
    assert msg == 'Only the PR author @the_auth or reviewers can request a review, not "commenter"'


def test_assign_author_not_reviewer(settings, gh_pr, gh_repo):
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='other'), id=123456),
        'user1',
        'org/repo',
        RepoConfig(reviewers=['user1', 'user2']),
        settings,
    )
    assert la.assign_author() == (False, 'Only reviewers "user1", "user2" can assign the author, not "other"')
    assert gh_pr.__history__ == []


def test_assign_author_no_reviewers(settings, gh_pr, gh_repo):
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='other'), id=123456),
        'user1',
        'org/repo',
        RepoConfig(),
        settings,
    )
    assert la.assign_author() == (False, 'Only reviewers (no reviewers configured) can assign the author, not "other"')
    assert gh_repo.__history__ == [
        "get_collaborators: Call() -> IterBlock('collaborators')",
        'get_collaborators.collaborators: Iter()',
    ]
    assert gh_pr.__history__ == []


def test_get_collaborators(settings, gh_pr):
    gh_repo = AttrBlock(
        'GhRepo',
        get_collaborators=CallableBlock(
            'get_collaborators',
            IterBlock(
                'collaborators', AttrBlock('Collaborator', login='colab1'), AttrBlock('Collaborator', login='colab2')
            ),
        ),
    )
    la = LabelAssign(
        gh_pr,
        gh_repo,
        'comment',
        Comment(body='x', user=User(login='colab2'), id=123456),
        'user1',
        'org/repo',
        RepoConfig(),
        settings,
    )
    act, msg = la.assign_author()
    assert act, msg
    assert msg == 'Author user1 successfully assigned to PR, "awaiting author revision" label added'
    assert gh_repo.__history__ == [
        (
            "get_collaborators: Call() -> IterBlock('collaborators', AttrBlock('Collaborator', login='colab1'), "
            "AttrBlock('Collaborator', login='colab2'))"
        ),
        (
            "get_collaborators.collaborators: Iter(AttrBlock('Collaborator', login='colab1'),"
            " AttrBlock('Collaborator', login='colab2'))"
        ),
    ]
    assert gh_pr.__history__ == [
        "get_issue_comment: Call(123456) -> AttrBlock('Comment', create_reaction=CallableBlock('create_reaction'))",
        "get_issue_comment.create_reaction: Call('+1')",
        "add_to_labels: Call('awaiting author revision')",
        "get_labels: Call() -> IterBlock('get_labels', AttrBlock('labels', name='ready for review'))",
        "get_labels: Iter(AttrBlock('labels', name='ready for review'))",
        "remove_from_labels: Call('ready for review')",
        "add_to_assignees: Call('user1')",
        "remove_from_assignees: Call('colab1', 'colab2')",
    ]


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


def build_gh(*, pr_files: tuple[AttrBlock, ...] = (), get_contents: CallableBlock = None):
    if get_contents is None:
        get_contents = CallableBlock('get_contents', raises=GithubException(404, 'Not Found', {}))

    return AttrBlock(
        'Gh',
        _requester=AttrBlock(
            'Requestor', _Requester__connection=AttrBlock('Connection', session=CallableBlock('session'))
        ),
        get_pull=CallableBlock(
            'get_pull',
            AttrBlock(
                'PullRequest',
                get_commits=CallableBlock(
                    'get_commits',
                    IterBlock('commits', None, AttrBlock('Commit', create_status=CallableBlock('create_status'))),
                ),
                get_files=CallableBlock('get_files', IterBlock('files', *pr_files)),
                base=AttrBlock(
                    'Base', ref='foobar', repo=AttrBlock('Repo', full_name='user/repo', get_contents=get_contents)
                ),
            ),
        ),
    )


def test_change_no_change_comment(settings, mocker):
    e = PullRequestUpdateEvent(
        action='opened',
        pull_request=PullRequest(number=123, state='open', user=User(login='foobar'), body='skip change file check'),
        repository=Repository(full_name='user/repo', owner=User(login='user1')),
    )
    gh = build_gh()
    mocker.patch('src.logic.get_repo_client', return_value=FakeGhContext(gh))
    act, msg = check_change_file(e, settings)
    assert act, msg
    assert msg == (
        '[Check change file] status set to "success" with description '
        '"Found "skip change file check" in Pull Request body"'
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
    gh = build_gh()
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
    get_contents = CallableBlock(
        'get_contents', AttrBlock('File', status='added', content=config_change_not_required, filename='.hooky.toml')
    )
    gh = build_gh(get_contents=get_contents)
    mocker.patch('src.logic.get_repo_client', return_value=FakeGhContext(gh))
    act, msg = check_change_file(e, settings)
    assert not act
    assert msg == '[Check change file] change file not required'


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
