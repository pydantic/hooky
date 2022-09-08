from time import time

import jwt
import redis
from cryptography.hazmat.backends import default_backend
from github import Github, Repository as GhRepository
from requests import Session

from .settings import Settings, log

__all__ = 'get_repo_client', 'GithubContext'
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
            return GithubContext(access_token, repo_full_name)

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
        return GithubContext(access_token, repo_full_name)


class GithubContext:
    def __init__(self, access_token: str, repo_full_name: str):
        self._gh = Github(access_token, base_url=github_base_url)
        self._repo = self._gh.get_repo(repo_full_name)

    def __enter__(self) -> GhRepository:
        return self._repo

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._gh._Github__requester._Requester__connection.session.close()
