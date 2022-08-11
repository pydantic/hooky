import re
from typing import Literal

from github import PullRequest as GhPullRequest
from pydantic import BaseModel

from .github_auth import get_client
from .settings import Settings, log

__all__ = 'process_event', 'Event'


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


def process_event(event: Event, settings: Settings) -> tuple[bool, str]:
    if isinstance(event, IssueEvent):
        if event.issue.pull_request is None:
            return False, 'action only applies to pull requests, not issues'

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
    elif isinstance(event, PullRequestUpdateEvent):
        return check_change_file(event, settings)
    else:
        return False, 'unknown event type'


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
        return False, 'review has no body'
    body = comment.body.lower()

    g = get_client(event.repository.owner.login, settings)
    gh_pr = g.get_repo(event.repository.full_name).get_pull(pr.number)

    log(f'{comment.user.login} ({event_type}): {body!r}')

    label_assign_ = LabelAssign(gh_pr, event_type, comment, pr.user.login, settings)
    if settings.request_review_trigger in body:
        action_taken, msg = label_assign_.request_review()
    elif settings.request_update_trigger in body or force_assign_author:
        action_taken, msg = label_assign_.assign_author()
    else:
        action_taken = False
        msg = (
            f'neither {settings.request_update_trigger!r} nor {settings.request_review_trigger!r} '
            f'found in comment body'
        )

    return action_taken, f'[Label and assign] {msg}'


class LabelAssign:
    def __init__(
        self,
        gh_pr: GhPullRequest,
        event_type: Literal['comment', 'review'],
        comment: Comment,
        author: str,
        settings: Settings,
    ):
        self.gh_pr = gh_pr
        self.event_type = event_type
        self.comment = comment
        self.commenter = comment.user.login
        self.author = author
        self.settings = settings
        self.commenter_is_reviewer = self.commenter in settings.reviewers

    def assign_author(self) -> tuple[bool, str]:
        if not self.commenter_is_reviewer:
            return False, f'Only reviewers {self.show_reviewers()} can assign the author, not {self.commenter}'

        self.add_reaction()
        self.gh_pr.add_to_labels(self.settings.awaiting_update_label)
        self.remove_label(self.settings.awaiting_review_label)
        self.gh_pr.add_to_assignees(self.author)
        to_remove = [r for r in self.settings.reviewers if r != self.author]
        if to_remove:
            self.gh_pr.remove_from_assignees(*to_remove)
        return (
            True,
            f'Author {self.author} successfully assigned to PR, "{self.settings.awaiting_update_label}" label added',
        )

    def request_review(self) -> tuple[bool, str]:
        commenter_is_author = self.author == self.commenter
        if not (self.commenter_is_reviewer or commenter_is_author):
            return False, f'Only the PR author {self.author} or reviewers can request a review, not {self.commenter}'

        self.add_reaction()
        self.gh_pr.add_to_labels(self.settings.awaiting_review_label)
        self.remove_label(self.settings.awaiting_update_label)
        self.gh_pr.add_to_assignees(*self.settings.reviewers)
        if self.author not in self.settings.reviewers:
            self.gh_pr.remove_from_assignees(self.author)
        return (
            True,
            f'Reviewers {self.show_reviewers()} successfully assigned to PR, '
            f'"{self.settings.awaiting_review_label}" label added',
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
        return ', '.join(f'"{r}"' for r in self.settings.reviewers)


closed_issue_template = r'(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+#{}'
required_actions = {'opened', 'edited', 'reopened', 'synchronize'}


def check_change_file(event: PullRequestUpdateEvent, settings: Settings) -> tuple[bool, str]:
    if event.pull_request.state != 'open':
        return False, '[Check change file] pull request is closed'
    if event.action not in required_actions:
        return False, f'[Check change file] file change not checked on "{event.action}"'

    log(f'[Check change file] action={event.action} pull-request=#{event.pull_request.number}')

    g = get_client(event.repository.owner.login, settings)
    gh_pr = g.get_repo(event.repository.full_name).get_pull(event.pull_request.number)

    body = event.pull_request.body.lower() if event.pull_request.body else ''
    if settings.no_change_file in body:
        return set_status(gh_pr, 'success', f'Found {settings.no_change_file!r} in pull request body')

    file_match = find_file(gh_pr)
    if file_match is None:
        return set_status(gh_pr, 'error', 'No change file found')

    file_id, file_author = file_match.groups()
    pr_author = event.pull_request.user.login
    if file_author.lower() != pr_author.lower():
        return set_status(gh_pr, 'error', f'File "{file_match.group()}" has wrong author, expected "{pr_author}"')

    if int(file_id) == event.pull_request.number:
        return set_status(gh_pr, 'success', 'Change file ID matches pull request ID')
    elif re.search(closed_issue_template.format(file_id), body):
        return set_status(gh_pr, 'success', 'Change file ID matches issue closed by the pull request')
    else:
        return set_status(gh_pr, 'error', 'Change file ID does not match pull request or closed issue')


def find_file(gh_pr: GhPullRequest) -> re.Match | None:
    for changed_file in gh_pr.get_files():
        if match := re.fullmatch(r'changes/(\d+)-(.+).md', changed_file.filename):
            return match


def set_status(
    gh_pr: GhPullRequest, state: Literal['error', 'failure', 'pending', 'success'], description: str
) -> tuple[bool, str]:
    *_, last_commit = gh_pr.get_commits()
    last_commit.create_status(
        state,
        description=description,
        target_url='https://github.com/pydantic/hooky#readme',
        context='change-file-checks',
    )
    return True, f'[Check change file] status set to "{state}" with description "{description}"'
