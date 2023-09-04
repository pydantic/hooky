import base64
from textwrap import indent

import redis
import rtoml
from github import GithubException
from github.Issue import Issue as GhIssue
from github.PullRequest import PullRequest as GhPullRequest
from github.Repository import Repository as GhRepository
from pydantic import BaseModel, ValidationError

from .settings import Settings, log

__all__ = ('RepoConfig',)


class RepoConfig(BaseModel):
    reviewers: list[str] = []
    request_update_trigger: str = 'please update'
    request_review_trigger: str = 'please review'
    awaiting_update_label: str = 'awaiting author revision'
    awaiting_review_label: str = 'ready for review'
    no_change_file: str = 'skip change file check'
    require_change_file: bool = True
    assignees: list[str] = []
    unconfirmed_label: str = 'unconfirmed'

    @classmethod
    def load(cls, *, pr: GhPullRequest | None = None, issue: GhIssue | None = None, settings: Settings) -> 'RepoConfig':
        assert (pr is None or issue is None) and pr != issue

        repo = pr.base.repo if pr is not None else issue.repository

        with redis.from_url(str(settings.redis_dsn)) as redis_client:
            repo_ref = pr.base.ref if pr is not None else repo.default_branch
            repo_cache_key = f'config_{repo.full_name}'

            if pr is not None:
                pr_cache_key = f'{repo_cache_key}_{repo_ref}'
                if pr_config := redis_client.get(pr_cache_key):
                    return RepoConfig.model_validate_json(pr_config)
                if pr_config := cls._load_raw(repo, ref=repo_ref):
                    redis_client.setex(pr_cache_key, settings.config_cache_timeout, pr_config.model_dump_json())
                    return pr_config

            if repo_config := redis_client.get(repo_cache_key):
                return RepoConfig.model_validate_json(repo_config)
            if repo_config := cls._load_raw(repo):
                redis_client.setex(repo_cache_key, settings.config_cache_timeout, repo_config.model_dump_json())
                return repo_config

            default_config = cls()
            redis_client.setex(repo_cache_key, settings.config_cache_timeout, default_config.model_dump_json())
            return default_config

    @classmethod
    def _load_raw(cls, repo: 'GhRepository', *, ref: str | None = None) -> 'RepoConfig | None':
        kwargs = {'ref': ref} if ref else {}
        prefix = f'{repo.full_name}#{ref}' if ref else f'{repo.full_name}#[default]'
        try:
            f = repo.get_contents('.hooky.toml', **kwargs)
            prefix += '/.hooky.toml'
        except GithubException:
            try:
                f = repo.get_contents('pyproject.toml', **kwargs)
                prefix += '/pyproject.toml'
            except GithubException as exc:
                log(f'{prefix}, No ".hooky.toml" or "pyproject.toml" found, using defaults: {exc}')
                return None

        content = base64.b64decode(f.content.encode())
        try:
            config = rtoml.loads(content.decode())
        except ValueError:
            log(f'{prefix}, Invalid config file, using defaults')
            return None
        try:
            hooky_config = config['tool']['hooky']
        except KeyError:
            log(f'{prefix}, No [tools.hooky] section found, using defaults')
            return None

        try:
            config = cls.model_validate(hooky_config)
        except ValidationError as e:
            log(f'{prefix}, Error validating hooky config, using defaults')
            log(indent(f'{type(e).__name__}: {e}', '  '))
            return None
        else:
            log(f'{prefix}, config: {config}')
            return config
