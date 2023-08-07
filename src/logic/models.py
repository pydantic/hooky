from pydantic import BaseModel, RootModel


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
    action: str  # not defining a Literal here as we're not going to handle an exhaustive list of possible values
    comment: Comment | None = None
    issue: Issue
    repository: Repository


class Review(BaseModel):
    body: str | None = None
    user: User
    state: str


class PullRequest(BaseModel):
    number: int
    user: User
    state: str
    body: str | None = None


class PullRequestReviewEvent(BaseModel):
    review: Review
    pull_request: PullRequest
    repository: Repository


class PullRequestUpdateEvent(BaseModel):
    action: str
    pull_request: PullRequest
    repository: Repository


Event = IssueEvent | PullRequestReviewEvent | PullRequestUpdateEvent


class EventParser(RootModel):
    root: Event
