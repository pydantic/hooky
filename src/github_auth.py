from time import time

import jwt
import redis
from cryptography.hazmat.backends import default_backend
from github import Github, PullRequest as GhPullRequest
from requests import Session

from .settings import Settings, log

__all__ = 'get_repo_client', 'close_github_session'
github_base_url = 'https://api.github.com'


def get_repo_client(repo_full_name: str, settings: Settings) -> GhPullRequest:
    """
    This could all be async, but since it's call from sync code (that can't be async because of GitHub)
    there's no point in making it async.
    """
    cache_key = f'github_access_token_{repo_full_name}'
    with redis.from_url(settings.redis_dsn) as redis_client:
        if access_token := redis_client.get(cache_key):
            access_token = access_token.decode()
            log(f'Using cached access token {access_token:.7}... for {repo_full_name}')
            return Github(access_token, base_url=github_base_url).get_repo(repo_full_name)

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
        return Github(access_token, base_url=github_base_url).get_repo(repo_full_name)


def close_github_session(gh: Github) -> None:
    """
    PyGithub is a complete shit-show.
    """
    gh._requester._Requester__connection.session.close()
