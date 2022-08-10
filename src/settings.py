from pydantic import BaseSettings, SecretBytes, SecretStr


class Settings(BaseSettings):
    access_token: SecretStr
    webhook_secret: SecretBytes
    reviewers: list[str] = ['samuelcolvin', 'PrettyWood', 'hramezani']
    request_update_trigger: str = 'please update'
    request_review_trigger: str = 'please review'
    awaiting_update_label: str = 'awaiting author updates'
    awaiting_review_label: str = 'awaiting review'
    no_change_file: str = 'skip change file check'


def log(msg: str) -> None:
    print(msg, flush=True)
