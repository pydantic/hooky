import enum
import re
import typing
from dataclasses import dataclass, field

import redis
from github.Issue import Issue as GhIssue
from github.Repository import Repository as GhRepository

from ..github_auth import get_repo_client
from ..repo_config import RepoConfig
from ..settings import Settings, log
from . import models


class IssueAction(str, enum.Enum):
    # TODO: Use StrEnum in Python 3.11
    OPENED = 'opened'
    REOPENED = 'reopened'


def process_issue(*, event: models.IssueEvent, settings: Settings) -> tuple[bool, str]:
    """Processes an issue in the repo

    Performs following actions:
    - assigns new/reopened issues to the next person in the assignees list

    TODO:
    - assign reopened issue to the assignee selected before
    - use "can confirm" magic comment from a contributor to change labels (remove an `unconfirmed` label)
    - use "please update" magic comment to reassign to the author
    - reassign from the author back to contributor after any author's comment
    """
    if event.action not in iter(IssueAction):
        return False, f'Ignored issue action "{event.action}"'

    with get_repo_client(event.repository.full_name, settings) as gh_repo:
        gh_issue = gh_repo.get_issue(event.issue.number)
        config = RepoConfig.load(issue=gh_issue, settings=settings)

        log(f'{event.issue.user} ({event.action}): #{event.issue.number}')

        label_assign = LabelAssign(
            gh_issue=gh_issue,
            gh_repo=gh_repo,
            action=IssueAction,
            author=event.issue.user,
            repo_fullname=event.repository.full_name,
            config=config,
            settings=settings,
        )

        label_assign.assign_new()

    return True, ''


@dataclass(kw_only=True)
class LabelAssign:
    # for example "Selected Assignee: @samuelcolvin"
    ASSIGNEE_REGEX: typing.ClassVar[re.Pattern] = re.compile(r'selected[ -]assignee:\s*@([\w\-]+)$', flags=re.I)

    gh_issue: GhIssue
    gh_repo: GhRepository
    action: IssueAction
    author: str
    repo_fullname: str
    config: RepoConfig
    settings: Settings
    assignees: list[str] = field(init=False)

    def __post_init__(self):
        self.assignees = self.config.assignees or [user.login for user in self.gh_repo.get_collaborators()]

    def assign_new(self):
        assignee = self._select_assignee()
        self._assign_user(assignee)
        self._add_label(self.config.unconfirmed_label)
        self._add_reaction()

        return (True, f'@{assignee} successfully assigned to issue, "{self.config.unconfirmed_label}" label added')

    def _select_assignee(self) -> str:
        key = f'assignee:{self.repo_fullname}'
        with redis.from_url(self.settings.redis_dsn) as redis_client:
            assignees_count = len(self.assignees)
            assignee_index = redis_client.incr(key) - 1

            # so that key never hits 2**64 and causes an error
            if assignee_index >= self.settings.index_multiple * assignees_count:
                assignee_index %= assignees_count
                redis_client.set(key, assignee_index)

            assignee = self.assignees[assignee_index % assignees_count]

        self.gh_issue.edit(body=f'{self.gh_issue.body}\n\nSelected Assignee: @{assignee}')
        return assignee

    def _assign_user(self, username: str) -> None:
        if username in (gh_user.login for gh_user in self.gh_issue.assignees):
            return
        self.gh_issue.add_to_assignees(username)

    def _add_label(self, label: str) -> None:
        if label in (gh_label.name for gh_label in self.gh_issue.labels):
            return
        self.gh_issue.add_to_labels(label)

    def _add_reaction(self) -> None:
        self.gh_issue.create_reaction('+1')
