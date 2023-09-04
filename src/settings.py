from pydantic import FilePath, RedisDsn, SecretBytes
from pydantic_settings import BaseSettings

__all__ = 'Settings', 'log'
_SETTINGS_CACHE: 'Settings | None' = None


class Settings(BaseSettings):
    github_app_id: str = '227243'
    github_app_secret_key: FilePath = 'github_app_secret_key.pem'
    webhook_secret: SecretBytes
    marketplace_webhook_secret: SecretBytes = None
    redis_dsn: RedisDsn = 'redis://localhost:6379'
    config_cache_timeout: int = 600
    reviewer_index_multiple: int = 1000

    @classmethod
    def load_cached(cls, **kwargs) -> 'Settings':
        """
        Allow settings to be set globally for testing.
        """
        global _SETTINGS_CACHE
        if _SETTINGS_CACHE is None:
            _SETTINGS_CACHE = cls(**kwargs)
        return _SETTINGS_CACHE


def log(msg: str) -> None:
    print(msg, flush=True)
