import pytest
import redis

from src.logic.issues import IssueAction, LabelAssign
from src.repo_config import RepoConfig

from .blocks import AttrBlock, CallableBlock, IterBlock


@pytest.fixture(name='gh_repo')
def fix_gh_repo():
    return AttrBlock('GhRepo', get_collaborators=CallableBlock('get_collaborators', IterBlock('collaborators')))


@pytest.fixture(name='gh_issue')
def fix_gh_issue():
    return AttrBlock(
        'GhIssue',
        edit=CallableBlock('edit'),
        body='this is the issue body',
        assignees=[],
        add_to_assignees=CallableBlock('add_to_assignees'),
        labels=[],
        add_to_labels=CallableBlock('add_to_labels'),
        create_reaction=CallableBlock('create_reaction'),
    )


def test_assign_new(settings, gh_issue, gh_repo, redis_cli):
    la = LabelAssign(
        gh_issue=gh_issue,
        gh_repo=gh_repo,
        action=IssueAction.OPENED,
        author='the_author',
        repo_fullname='org/repo',
        config=RepoConfig(assignees=['user1', 'user2']),
        settings=settings,
    )
    acted, msg = la.assign_new()
    assert acted, msg
    assert msg == '@user1 successfully assigned to issue, "unconfirmed" label added'
    assert gh_issue.__history__ == [
        "edit: Call(body='this is the issue body\\n\\nSelected Assignee: @user1')",
        "add_to_assignees: Call('user1')",
        "add_to_labels: Call('unconfirmed')",
        "create_reaction: Call('+1')",
    ]

    la2 = LabelAssign(
        gh_issue=gh_issue,
        gh_repo=gh_repo,
        action=IssueAction.OPENED,
        author='the_author',
        repo_fullname='org/repo',
        config=RepoConfig(assignees=['user1', 'user2']),
        settings=settings,
    )
    acted, msg = la2.assign_new()
    assert acted, msg
    assert msg == '@user2 successfully assigned to issue, "unconfirmed" label added'


def test_assign_new_one_assignee(settings, gh_issue, gh_repo, redis_cli):
    la = LabelAssign(
        gh_issue=gh_issue,
        gh_repo=gh_repo,
        action=IssueAction.OPENED,
        author='the_author',
        repo_fullname='org/repo',
        config=RepoConfig(assignees=['user1']),
        settings=settings,
    )
    acted, msg = la.assign_new()
    assert acted, msg
    assert msg == '@user1 successfully assigned to issue, "unconfirmed" label added'
    assert gh_issue.__history__ == [
        "edit: Call(body='this is the issue body\\n\\nSelected Assignee: @user1')",
        "add_to_assignees: Call('user1')",
        "add_to_labels: Call('unconfirmed')",
        "create_reaction: Call('+1')",
    ]


def test_many_assignments(settings, gh_issue, gh_repo, redis_cli: redis.Redis):
    la = LabelAssign(
        gh_issue=gh_issue,
        gh_repo=gh_repo,
        action=IssueAction.OPENED,
        author='the_author',
        repo_fullname='org/repo',
        config=RepoConfig(assignees=['user1', 'user2', 'user3', 'user4']),
        settings=settings,
    )

    key = 'assignee:org/repo'
    assert redis_cli.get(key) is None

    assert la._select_assignee() == 'user1'
    assert la._select_assignee() == 'user2'
    assert la._select_assignee() == 'user3'
    assert la._select_assignee() == 'user4'
    assert la._select_assignee() == 'user1'
    assert la._select_assignee() == 'user2'

    redis_cli.set(key, 4_294_967_295)
    assert la._select_assignee() == 'user4'
    assert redis_cli.get(key) == b'4294967296'
    assert la._select_assignee() == 'user1'
    assert redis_cli.get(key) == b'1'
    assert la._select_assignee() == 'user2'
    assert la._select_assignee() == 'user3'
    assert la._select_assignee() == 'user4'
    assert la._select_assignee() == 'user1'

    redis_cli.set(key, 4_294_967_299)
    assert la._select_assignee() == 'user4'
    assert redis_cli.get(key) == b'4'

    redis_cli.set(key, 4_294_967_300)
    assert la._select_assignee() == 'user1'
    assert redis_cli.get(key) == b'1'
