from __future__ import annotations

import re
import typing


class BaseActor:
    ROLE: typing.ClassVar[str]
    _ROLE_REGEX: typing.ClassVar[re.Pattern] | None = None

    @classmethod
    def _get_role_regex(cls) -> re.Pattern:
        if cls._ROLE_REGEX is None:
            # for example "Selected Assignee: @samuelcolvin" or "Selected Reviewer: @samuelcolvin"
            cls._ROLE_REGEX = re.compile(rf'selected[ -]{cls.ROLE}:\s*@([\w\-]+)$', flags=re.I)
        return cls._ROLE_REGEX
