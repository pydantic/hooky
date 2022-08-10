from typing import cast

from github import Github, PullRequest as GhPullRequest
from pydantic import BaseModel

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


class PullRequestEvent(BaseModel):
    review: Review
    pull_request: PullRequest
    repository: Repository


Event = IssueEvent | PullRequestEvent


def process_event(event: Event, settings: Settings) -> tuple[bool, str]:
    force_assign_author = False

    if hasattr(event, 'issue'):
        event = cast(IssueEvent, event)
        if event.issue.pull_request is None:
            return False, 'action only applies to pull requests, not issues'

        comment = event.comment
        pr = event.issue
        event_type = 'comment'
    else:
        event = cast(PullRequestEvent, event)
        comment = event.review
        if comment.body is None:
            return False, 'review has no body'
        pr = event.pull_request
        force_assign_author = event.review.state == 'changes_requested'
        event_type = 'review'

    commenter = comment.user.login
    body = comment.body.lower()

    g = Github(settings.access_token.get_secret_value())
    gh_pr = g.get_repo(event.repository.full_name).get_pull(pr.number)

    log(f'{commenter} ({event_type}): {body!r}')

    p = ProcessFunctions(gh_pr, comment, pr.user.login, settings)
    if settings.request_review_trigger in body:
        action_taken, msg = p.request_review()
    elif settings.request_update_trigger in body or force_assign_author:
        action_taken, msg = p.assign_author()
    else:
        action_taken = False
        msg = (
            f'neither {settings.request_update_trigger!r} nor {settings.request_review_trigger!r} '
            f'found in comment body, not proceeding'
        )
    if action_taken:
        p.add_reaction(event_type)

    return action_taken, msg


class ProcessFunctions:
    def __init__(self, gh_pr: GhPullRequest, comment: Comment, author: str, settings: Settings):
        self.gh_pr = gh_pr
        self.comment = comment
        self.commenter = comment.user.login
        self.author = author
        self.settings = settings
        self.commenter_is_reviewer = self.commenter in settings.reviewers

    def assign_author(self) -> tuple[bool, str]:
        if not self.commenter_is_reviewer:
            return (
                False,
                f'Only reviewers {self.show_reviewers()} can assign the author, not {self.commenter}',
            )
        self.gh_pr.add_to_labels(self.settings.awaiting_update_label)
        self.remove_label(self.settings.awaiting_review_label)
        self.gh_pr.add_to_assignees(self.author)
        to_remove = [r for r in self.settings.reviewers if r != self.author]
        if to_remove:
            self.gh_pr.remove_from_assignees(*to_remove)
        return (
            True,
            f'Author {self.author} successfully assigned to PR, '
            f'"{self.settings.awaiting_update_label}" label added',
        )

    def request_review(self) -> tuple[bool, str]:
        commenter_is_author = self.author == self.commenter
        if not (self.commenter_is_reviewer or commenter_is_author):
            return False, (
                f'Only the PR author {self.author} or reviewers can request a review, not {self.commenter}'
            )
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

    def add_reaction(self, event_type: str) -> None:
        """
        Currently it seems there's no way to create a reaction on a review body, only on issue comments
        and review comments, although it's possible in the UI
        """
        if event_type == 'comment':
            self.gh_pr.get_issue_comment(self.comment.id).create_reaction('+1')

    def remove_label(self, label: str):
        labels = self.gh_pr.get_labels()
        if any(lb.name == label for lb in labels):
            self.gh_pr.remove_from_labels(label)

    def show_reviewers(self):
        return ', '.join(f'"{r}"' for r in self.settings.reviewers)
