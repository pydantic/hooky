from pydantic import BaseSettings, SecretBytes, SecretStr


class Settings(BaseSettings):
    access_token: SecretStr
    webhook_secret: SecretBytes
    reviewers: list[str] = ['samuelcolvin']
    request_update_trigger: str = 'please update'
    request_review_trigger: str = 'please review'
    awaiting_update_label: str = 'awaiting author updates'
    awaiting_review_label: str = 'awaiting review'


def log(msg: str) -> None:
    print(msg, flush=True)
