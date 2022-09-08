import base64
from dataclasses import dataclass
from textwrap import indent
from time import time

import jwt
import redis
import rtoml
from cryptography.hazmat.backends import default_backend
from github import Github, GithubException, PullRequest as GhPullRequest
from pydantic import BaseModel, ValidationError
from requests import Session

from .settings import Settings, log

__all__ = 'get_repo_client', 'GithubContext', 'RepoConfig'
github_base_url = 'https://api.github.com'


def get_repo_client(repo_full_name: str, settings: Settings) -> 'GithubContext':
    """
    This could all be async, but since it's call from sync code (that can't be async because of GitHub)
    there's no point in making it async.
    """
    with redis.from_url(settings.redis_dsn) as redis_client:
        cache_key = f'github_access_token_{repo_full_name}'
        if access_token := redis_client.get(cache_key):
            access_token = access_token.decode()
            log(f'Using cached access token {access_token:.7}... for {repo_full_name}')
            return GithubContext(redis_client, access_token, repo_full_name)

        pem_bytes = settings.github_app_secret_key.read_bytes()

        private_key = default_backend().load_pem_private_key(pem_bytes, None)

        now = int(time())
        payload = {'iat': now - 30, 'exp': now + 60, 'iss': settings.github_app_id}
        jwt_value = jwt.encode(payload, private_key, algorithm='RS256')

        with Session() as session:
            session.headers.update({'Authorization': f'Bearer {jwt_value}', 'Accept': 'application/vnd.github+json'})
            r = session.get(f'{github_base_url}/repos/{repo_full_name}/installation')
            r.raise_for_status()
            installation_id = r.json()['id']

            r = session.post(f'{github_base_url}/app/installations/{installation_id}/access_tokens')
            r.raise_for_status()
            access_token = r.json()['token']

        # access token's lifetime is 1 hour
        # https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app
        redis_client.setex(cache_key, 3600 - 100, access_token)
        log(f'Created new access token {access_token:.7}... for {repo_full_name}')
        return GithubContext(redis_client, access_token, repo_full_name)


class RepoConfig(BaseModel):
    reviewers: list[str] = []
    request_update_trigger: str = 'please update'
    request_review_trigger: str = 'please review'
    awaiting_update_label: str = 'awaiting author revision'
    awaiting_review_label: str = 'ready for review'
    no_change_file: str = 'skip change file check'
    require_change_file: bool = True


@dataclass
class GithubRepo:
    repo: GhPullRequest
    config: RepoConfig


class GithubContext:
    def __init__(self, redis_client: redis.Redis, access_token: str, repo_full_name: str):
        self._gh = Github(access_token, base_url=github_base_url)
        repo = self._gh.get_repo(repo_full_name)
        config = get_cached_config(redis_client, repo_full_name, repo)
        self._gh_repo = GithubRepo(repo, config)

    def __enter__(self) -> GithubRepo:
        return self._gh_repo

    def __exit__(self, exc_type, exc_val, exc_tb):
        if gh := self._gh:  # pragma: no branch
            gh._Github__requester._Requester__connection.session.close()


def get_cached_config(redis_client: redis.Redis, repo_full_name: str, repo: GhPullRequest) -> RepoConfig:
    cache_key = f'config_{repo_full_name}'
    if config := redis_client.get(cache_key):
        return RepoConfig.parse_raw(config)

    config = get_config(repo) or RepoConfig()
    redis_client.setex(cache_key, 300, config.json())
    return config


def get_config(repo: GhPullRequest) -> RepoConfig | None:
    try:
        f = repo.get_contents('pyproject.toml')
    except GithubException as exc:
        log(f'No pyproject.toml found, using defaults: {exc}')
        return None

    content = base64.b64decode(f.content.encode())
    try:
        config = rtoml.loads(content.decode())
    except ValueError:
        log('Invalid pyproject.toml, using defaults')
        return None
    try:
        hooky_config = config['tool']['hooky']
    except KeyError:
        log('No [tools.hooky] section found, using defaults')
        return None

    try:
        return RepoConfig.parse_obj(hooky_config)
    except ValidationError as e:
        log('Error validating hooky config, using defaults')
        log(indent(f'{type(e).__name__}: {e}', '  '))
        return None
