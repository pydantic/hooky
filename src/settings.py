from pydantic import BaseSettings, FilePath, RedisDsn, SecretBytes


class Settings(BaseSettings):
    github_app_id: str = '227243'
    github_app_secret_key: FilePath = 'github_app_secret_key.pem'
    webhook_secret: SecretBytes
    redis_dsn: RedisDsn = 'redis://localhost:6379'
    reviewers: list[str] = ['samuelcolvin', 'PrettyWood', 'hramezani']
    request_update_trigger: str = 'please update'
    request_review_trigger: str = 'please review'
    awaiting_update_label: str = 'awaiting author revision'
    awaiting_review_label: str = 'ready for review'
    no_change_file: str = 'skip change file check'


def log(msg: str) -> None:
    print(msg, flush=True)
