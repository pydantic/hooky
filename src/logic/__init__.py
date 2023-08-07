from textwrap import indent

from ..settings import Settings, log
from . import issues, prs
from .models import EventParser, IssueEvent, PullRequestReviewEvent, PullRequestUpdateEvent

__all__ = ('process_event',)


def process_event(request_body: bytes, settings: Settings) -> tuple[bool, str]:
    try:
        event = EventParser.model_validate_json(request_body).root
    except ValueError as e:
        log(indent(f'{type(e).__name__}: {e}', '  '))
        return False, 'Error parsing request body'

    if isinstance(event, IssueEvent):
        if event.issue.pull_request is None:
            return issues.process_issue(event=event, settings=settings)

        return prs.label_assign(
            event=event,
            event_type='comment',
            pr=event.issue,
            comment=event.comment,
            force_assign_author=False,
            settings=settings,
        )
    elif isinstance(event, PullRequestReviewEvent):
        return prs.label_assign(
            event=event,
            event_type='review',
            pr=event.pull_request,
            comment=event.review,
            force_assign_author=event.review.state == 'changes_requested',
            settings=settings,
        )
    else:
        assert isinstance(event, PullRequestUpdateEvent), 'unknown event type'
        return prs.check_change_file(event, settings)
