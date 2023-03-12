import random
import re
from textwrap import indent
from typing import Literal

from github import PullRequest as GhPullRequest, Repository as GhRepository
from pydantic import BaseModel, parse_raw_as

from .github_auth import get_repo_client
from .repo_config import RepoConfig
from .settings import Settings, log

import redis

__all__ = ('process_event',)


class User(BaseModel):
    login: str


class Comment(BaseModel):
    body: str
    user: User
    id: int


class IssuePullRequest(BaseModel):
    url: str


class Issue(BaseModel):
    pull_request: IssuePullRequest | None = None
    user: User
    number: int
    body: str = ''


class Repository(BaseModel):
    full_name: str
    owner: User


class IssueEvent(BaseModel):
    comment: Comment
    issue: Issue
    repository: Repository


class Review(BaseModel):
    body: str | None
    user: User
    state: str


class PullRequest(BaseModel):
    number: int
    user: User
    state: str
    body: str | None


class PullRequestReviewEvent(BaseModel):
    review: Review
    pull_request: PullRequest
    repository: Repository


class PullRequestUpdateEvent(BaseModel):
    action: str
    pull_request: PullRequest
    repository: Repository


Event = IssueEvent | PullRequestReviewEvent | PullRequestUpdateEvent


def process_event(request_body: bytes, settings: Settings) -> tuple[bool, str]:
    try:
        event = parse_raw_as(Event, request_body)  # type: ignore
    except ValueError as e:
        log(indent(f'{type(e).__name__}: {e}', '  '))
        return False, 'Error parsing request body'

    if isinstance(event, IssueEvent):
        if event.issue.pull_request is None:
            return False, 'action only applies to Pull Requests, not Issues'

        return label_assign(
            event=event,
            event_type='comment',
            pr=event.issue,
            comment=event.comment,
            force_assign_author=False,
            settings=settings,
        )
    elif isinstance(event, PullRequestReviewEvent):
        return label_assign(
            event=event,
            event_type='review',
            pr=event.pull_request,
            comment=event.review,
            force_assign_author=event.review.state == 'changes_requested',
            settings=settings,
        )
    else:
        assert isinstance(event, PullRequestUpdateEvent), 'unknown event type'
        return check_change_file(event, settings)


def label_assign(
    *,
    event: Event,
    event_type: Literal['comment', 'review'],
    pr: Issue | PullRequest,
    comment: Comment | Review,
    force_assign_author: bool,
    settings: Settings,
) -> tuple[bool, str]:
    if comment.body is None:
        return False, '[Label and assign] review has no body'
    body = comment.body.lower()

    with get_repo_client(event.repository.full_name, settings) as gh_repo:
        gh_pr = gh_repo.get_pull(pr.number)
        config = RepoConfig.load(gh_pr, settings)
        log(f'{comment.user.login} ({event_type}): {body!r}')

        label_assign_ = LabelAssign(gh_pr, gh_repo, event_type, comment, pr.user.login, config, settings)
        pr = label_assign_.parse_magic_string(pr, settings)
        if config.request_review_trigger in body:
            action_taken, msg = label_assign_.request_review()
        elif config.request_update_trigger in body or force_assign_author:
            action_taken, msg = label_assign_.assign_author()
        else:
            action_taken = False
            msg = (
                f'neither {config.request_update_trigger!r} nor {config.request_review_trigger!r} '
                f'found in comment body'
            )
    return action_taken, f'[Label and assign] {msg}'


class LabelAssign:
    def __init__(
        self,
        gh_pr: GhPullRequest,
        gh_repo: GhRepository,
        event_type: Literal['comment', 'review'],
        comment: Comment,
        author: str,
        config: RepoConfig,
        settings: Settings,
    ):
        self.gh_pr = gh_pr
        self.event_type = event_type
        self.comment = comment
        self.commenter = comment.user.login
        self.author = author
        self.config = config
        self.settings = settings
        if config.reviewers:
            self.reviewers = config.reviewers
        else:
            self.reviewers = [r.login for r in gh_repo.get_collaborators()]
        self.commenter_is_reviewer = self.commenter in self.reviewers

    def assign_author(self) -> tuple[bool, str]:
        if not self.commenter_is_reviewer:
            return False, f'Only reviewers {self.show_reviewers()} can assign the author, not "{self.commenter}"'

        self.add_reaction()
        self.gh_pr.add_to_labels(self.config.awaiting_update_label)
        self.remove_label(self.config.awaiting_review_label)
        self.gh_pr.add_to_assignees(self.author)
        to_remove = [r for r in self.reviewers if r != self.author]
        if to_remove:
            self.gh_pr.remove_from_assignees(*to_remove)
        return (
            True,
            f'Author {self.author} successfully assigned to PR, "{self.config.awaiting_update_label}" label added',
        )

    def parse_magic_string(self, pull_request: Issue | PullRequest, settings: Settings) -> Issue | PullRequest:
        """
        Parses the PR body to find magic string

        :param pull_request_body: Accepts either Issue or Pull Request. Required to parse body contents.
        :param settings: Settings to access redis.
        :return: returns text to be appended to the pull request body.
        """
        self.gh_pr.remove_from_assignees(self.author)  # remove author from assignees

        with redis.from_url(settings.redis_dsn) as redis_client:
            if (isinstance(pull_request, PullRequest)) and pull_request.body is not None:  # only PullRequest class has body
                search_username = re.search(r'primary-reviewer:\s@[a-zA-Z][a-zA-Z0-9-_\.]{1,20}$', pull_request.body)
                if search_username: # found magic comment
                    username = search_username[0].split('@')[1]
                    redis_client.set('hooky_last_assigned_reviwer', username)
                    self.gh_pr.add_to_assignees(username)
                    return pull_request

            if redis_client.exists('hooky_last_assigned_reviwer'):  # if last reviewer exists
                last_assignee = redis_client.get('hooky_last_assigned_reviwer')
                self.gh_pr.remove_from_assignees(last_assignee)  # remove last assigned from assignees

            username = random.choice(self.reviewers)  # allot to random user
            redis_client.set('hooky_last_assigned_reviwer', username)
            # pull_request.body += "\n\nprimary-reviewer:{}".format(username)
            return pull_request

    def request_review(self) -> tuple[bool, str]:
        commenter_is_author = self.author == self.commenter
        if not (self.commenter_is_reviewer or commenter_is_author):
            return False, f'Only the PR author {self.author} or reviewers can request a review, not "{self.commenter}"'

        self.add_reaction()
        self.gh_pr.add_to_labels(self.config.awaiting_review_label)
        self.remove_label(self.config.awaiting_update_label)
        # self.gh_pr.add_to_assignees(*self.reviewers)
        if self.author not in self.reviewers:
            self.gh_pr.remove_from_assignees(self.author)

        return (
            True,
            f'Reviewers {self.show_reviewers()} successfully assigned to PR, '
            f'"{self.config.awaiting_review_label}" label added',
        )

    def add_reaction(self) -> None:
        """
        Currently it seems there's no way to create a reaction on a review body, only on issue comments
        and review comments, although it's possible in the UI
        """
        if self.event_type == 'comment':
            self.gh_pr.get_issue_comment(self.comment.id).create_reaction('+1')

    def remove_label(self, label: str):
        labels = self.gh_pr.get_labels()
        if any(lb.name == label for lb in labels):
            self.gh_pr.remove_from_labels(label)

    def show_reviewers(self):
        if self.reviewers:
            return ', '.join(f'"{r}"' for r in self.reviewers)
        else:
            return '(no reviewers configured)'


closed_issue_template = (
    r'(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+'
    r'(#|https://github.com/[^/]+/[^/]+/issues/){}'
)
required_actions = {'opened', 'edited', 'reopened', 'synchronize'}
CommitStatus = Literal['error', 'failure', 'pending', 'success']


def check_change_file(event: PullRequestUpdateEvent, settings: Settings) -> tuple[bool, str]:
    if event.pull_request.state != 'open':
        return False, f'[Check change file] Pull Request is {event.pull_request.state}, not open'
    if event.action not in required_actions:
        return False, f'[Check change file] file change not checked on "{event.action}"'
    if event.pull_request.user.login.endswith('[bot]'):
        return False, '[Check change file] Pull Request author is a bot'

    log(f'[Check change file] action={event.action} pull-request=#{event.pull_request.number}')
    with get_repo_client(event.repository.full_name, settings) as gh_repo:
        gh_pr = gh_repo.get_pull(event.pull_request.number)
        config = RepoConfig.load(gh_pr, settings)
        if not config.require_change_file:
            return False, '[Check change file] change file not required'

        body = event.pull_request.body.lower() if event.pull_request.body else ''
        if config.no_change_file in body:
            return set_status(gh_pr, 'success', f'Found "{config.no_change_file}" in Pull Request body')
        elif file_match := find_change_file(gh_pr):
            return set_status(gh_pr, *check_change_file_content(file_match, body, event.pull_request))
        else:
            return set_status(gh_pr, 'error', 'No change file found')


def check_change_file_content(file_match: re.Match, body: str, pr: PullRequest) -> tuple[CommitStatus, str]:
    file_id, file_author = file_match.groups()
    pr_author = pr.user.login
    if file_author.lower() != pr_author.lower():
        return 'error', f'File "{file_match.group()}" has wrong author, expected "{pr_author}"'
    elif int(file_id) == pr.number:
        return 'success', f'Change file ID #{file_id} matches the Pull Request'
    elif re.search(closed_issue_template.format(file_id), body):
        return 'success', f'Change file ID #{file_id} matches Issue closed by the Pull Request'
    else:
        return 'error', 'Change file ID does not match Pull Request or closed Issue'


def find_change_file(gh_pr: GhPullRequest) -> re.Match | None:
    for changed_file in gh_pr.get_files():
        if changed_file.status == 'added' and (match := re.fullmatch(r'changes/(\d+)-(.+).md', changed_file.filename)):
            return match


def set_status(gh_pr: GhPullRequest, state: CommitStatus, description: str) -> tuple[bool, str]:
    *_, last_commit = gh_pr.get_commits()
    last_commit.create_status(
        state,
        description=description,
        target_url='https://github.com/pydantic/hooky#readme',
        context='change-file-checks',
    )
    return True, f'[Check change file] status set to "{state}" with description "{description}"'
