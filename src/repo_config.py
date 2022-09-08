import base64
from textwrap import indent

import redis
import rtoml
from github import GithubException, PullRequest as GhPullRequest, Repository as GhRepository
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

    @classmethod
    def load(cls, pr: GhPullRequest, settings: Settings) -> 'RepoConfig':
        repo = pr.base.repo
        with redis.from_url(settings.redis_dsn) as redis_client:
            pr_base_ref = pr.base.ref
            pr_cache_key = f'config_{repo.full_name}_{pr_base_ref}'
            repo_cache_key = f'config_{repo.full_name}'
            if pr_config := redis_client.get(pr_cache_key):
                return RepoConfig.parse_raw(pr_config)
            elif pr_config := cls._load_raw(repo, ref=pr_base_ref):
                redis_client.setex(pr_cache_key, 300, pr_config.json())
                return pr_config
            elif repo_config := redis_client.get(repo_cache_key):
                return RepoConfig.parse_raw(repo_config)
            elif repo_config := cls._load_raw(repo):
                redis_client.setex(repo_cache_key, 300, repo_config.json())
                return repo_config
            else:
                return cls()

    @classmethod
    def _load_raw(cls, repo: 'GhRepository', *, ref: str | None = None) -> 'RepoConfig | None':
        kwargs = {'ref': ref} if ref else {}
        try:
            f = repo.get_contents('pyproject.toml', **kwargs)
        except GithubException as exc:
            log(f'{repo.full_name}#{ref}, No pyproject.toml found, using defaults: {exc}')
            return None

        content = base64.b64decode(f.content.encode())
        try:
            config = rtoml.loads(content.decode())
        except ValueError:
            log(f'{repo.full_name}#{ref}, Invalid pyproject.toml, using defaults')
            return None
        try:
            hooky_config = config['tool']['hooky']
        except KeyError:
            log(f'{repo.full_name}#{ref}, No [tools.hooky] section found, using defaults')
            return None

        try:
            return cls.parse_obj(hooky_config)
        except ValidationError as e:
            log(f'{repo.full_name}#{ref}, Error validating hooky config, using defaults')
            log(indent(f'{type(e).__name__}: {e}', '  '))
            return None
